using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Jellyfin.Plugin.AutoFix.Common;
using Jellyfin.Plugin.AutoFix.Services;
using MediaBrowser.Controller.Entities.Movies;
using MediaBrowser.Controller.Providers;
using MediaBrowser.Model.Entities;
using MediaBrowser.Model.Providers;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.AutoFix.Providers;

/// <summary>
/// Pre-scanning metadata provider that cleans messy titles and resolves TMDb metadata.
/// </summary>
public class AutoFixMovieMetadataProvider : IRemoteMetadataProvider<Movie, MovieInfo>, IHasOrder
{
    private readonly TmdbClient _tmdbClient;
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly ILogger<AutoFixMovieMetadataProvider> _logger;

    public AutoFixMovieMetadataProvider(
        IHttpClientFactory httpClientFactory,
        ILogger<AutoFixMovieMetadataProvider> logger)
    {
        _httpClientFactory = httpClientFactory;
        _logger = logger;
        _tmdbClient = new TmdbClient(httpClientFactory, LoggerFactory.Create(builder => { }).CreateLogger<TmdbClient>());
    }

    /// <inheritdoc />
    public string Name => "AutoFix";

    /// <inheritdoc />
    /// <remarks>
    /// Lower order value ensures this provider executes before default providers.
    /// </remarks>
    public int Order => -10;

    /// <inheritdoc />
    public async Task<MetadataResult<Movie>> GetMetadata(MovieInfo info, CancellationToken cancellationToken)
    {
        var result = new MetadataResult<Movie>
        {
            Item = new Movie()
        };

        var config = Plugin.Instance?.Configuration;
        bool sanitizerEnabled = config?.EnableSanitizer ?? true;
        string? customTags = config?.CustomTagsToStrip;

        int? tmdbId = null;

        // 1. Check if TMDb ID is already set
        if (info.ProviderIds.TryGetValue(MetadataProvider.Tmdb.ToString(), out var existingId)
            && int.TryParse(existingId, out var parsedId))
        {
            tmdbId = parsedId;
        }

        // 2. If no TMDb ID, sanitize filename and search TMDb
        if (!tmdbId.HasValue)
        {
            string rawToParse = !string.IsNullOrWhiteSpace(info.Name) ? info.Name : Path.GetFileNameWithoutExtension(info.Path ?? string.Empty);

            var parsed = sanitizerEnabled
                ? CleanTitleParser.Parse(rawToParse, customTags)
                : new ParsedTitleInfo(rawToParse, info.Year, rawToParse, false);

            string searchTitle = parsed.CleanTitle;
            int? searchYear = parsed.Year ?? info.Year;

            _logger.LogInformation("AutoFix: Processing '{Raw}' -> Cleaned title: '{Clean}' ({Year})",
                rawToParse, searchTitle, searchYear);

            var searchResults = await _tmdbClient.SearchMovieAsync(searchTitle, searchYear, cancellationToken).ConfigureAwait(false);

            if (searchResults.Count > 0)
            {
                var bestMatch = searchResults[0];
                tmdbId = bestMatch.Id;
                _logger.LogInformation("AutoFix: Resolved '{Title}' to TMDb ID {TmdbId}", searchTitle, tmdbId);
            }
            else
            {
                _logger.LogWarning("AutoFix: No TMDb match found for '{Title}' ({Year})", searchTitle, searchYear);
            }
        }

        // 3. Populate metadata from TMDb details
        if (tmdbId.HasValue)
        {
            var details = await _tmdbClient.GetMovieDetailsAsync(tmdbId.Value, cancellationToken).ConfigureAwait(false);
            if (details != null)
            {
                result.HasMetadata = true;
                result.Item.Name = details.Title;
                result.Item.OriginalTitle = details.OriginalTitle;
                result.Item.Overview = details.Overview;

                if (DateTime.TryParse(details.ReleaseDate, CultureInfo.InvariantCulture, DateTimeStyles.None, out var premiereDate))
                {
                    result.Item.PremiereDate = premiereDate;
                    result.Item.ProductionYear = premiereDate.Year;
                }

                result.Item.CommunityRating = details.VoteAverage;
                result.Item.SetProviderId(MetadataProvider.Tmdb, details.Id.ToString(CultureInfo.InvariantCulture));

                if (!string.IsNullOrWhiteSpace(details.ImdbId))
                {
                    result.Item.SetProviderId(MetadataProvider.Imdb, details.ImdbId);
                }

                // 4. Optional In-Place Renaming on disk if enabled
                if (config?.EnableInPlaceRenaming == true && !string.IsNullOrWhiteSpace(info.Path) && File.Exists(info.Path))
                {
                    TryInPlaceRename(info.Path, details.Title, result.Item.ProductionYear, details.Id);
                }
            }
        }

        return result;
    }

    /// <inheritdoc />
    public async Task<IEnumerable<RemoteSearchResult>> GetSearchResults(MovieInfo searchInfo, CancellationToken cancellationToken)
    {
        string raw = !string.IsNullOrWhiteSpace(searchInfo.Name) ? searchInfo.Name : Path.GetFileNameWithoutExtension(searchInfo.Path ?? string.Empty);
        var parsed = CleanTitleParser.Parse(raw, Plugin.Instance?.Configuration.CustomTagsToStrip);

        var results = await _tmdbClient.SearchMovieAsync(parsed.CleanTitle, parsed.Year ?? searchInfo.Year, cancellationToken).ConfigureAwait(false);

        return results.Select(r =>
        {
            int? prodYear = null;
            if (DateTime.TryParse(r.ReleaseDate, CultureInfo.InvariantCulture, DateTimeStyles.None, out var d))
            {
                prodYear = d.Year;
            }

            var item = new RemoteSearchResult
            {
                Name = r.Title,
                ProductionYear = prodYear,
                Overview = r.Overview,
                ImageUrl = !string.IsNullOrEmpty(r.PosterPath) ? $"https://image.tmdb.org/t/p/w500{r.PosterPath}" : null
            };

            item.SetProviderId(MetadataProvider.Tmdb, r.Id.ToString(CultureInfo.InvariantCulture));
            return item;
        });
    }

    /// <inheritdoc />
    public Task<HttpResponseMessage> GetImageResponse(string url, CancellationToken cancellationToken)
    {
        var client = _httpClientFactory.CreateClient();
        return client.GetAsync(url, cancellationToken);
    }

    private void TryInPlaceRename(string currentPath, string cleanTitle, int? year, int tmdbId)
    {
        try
        {
            string dir = Path.GetDirectoryName(currentPath) ?? string.Empty;
            string ext = Path.GetExtension(currentPath);

            // Sanitize illegal filesystem characters
            char[] invalidChars = Path.GetInvalidFileNameChars();
            string safeTitle = new string(cleanTitle.Select(c => invalidChars.Contains(c) ? '_' : c).ToArray());

            string yearPart = year.HasValue ? $" ({year.Value})" : string.Empty;
            string newFileName = $"{safeTitle}{yearPart} [tmdbid-{tmdbId}]{ext}";
            string newPath = Path.Combine(dir, newFileName);

            if (!string.Equals(currentPath, newPath, StringComparison.OrdinalIgnoreCase) && !File.Exists(newPath))
            {
                File.Move(currentPath, newPath);
                _logger.LogInformation("AutoFix: In-place renamed file from '{Old}' to '{New}'", currentPath, newPath);
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "AutoFix: Failed to in-place rename '{CurrentPath}'", currentPath);
        }
    }
}
