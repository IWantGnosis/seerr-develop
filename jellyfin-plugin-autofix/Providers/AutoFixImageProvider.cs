using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Jellyfin.Plugin.AutoFix.Common;
using Jellyfin.Plugin.AutoFix.Services;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.Movies;
using MediaBrowser.Controller.Providers;
using MediaBrowser.Model.Entities;
using MediaBrowser.Model.Providers;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.AutoFix.Providers;

/// <summary>
/// Remote image provider that fetches and injects posters, backdrops, and logos from TMDb.
/// </summary>
public class AutoFixImageProvider : IRemoteImageProvider, IHasOrder
{
    private readonly TmdbClient _tmdbClient;
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly ILogger<AutoFixImageProvider> _logger;

    public AutoFixImageProvider(
        IHttpClientFactory httpClientFactory,
        ILogger<AutoFixImageProvider> logger)
    {
        _httpClientFactory = httpClientFactory;
        _logger = logger;
        _tmdbClient = new TmdbClient(httpClientFactory, LoggerFactory.Create(builder => { }).CreateLogger<TmdbClient>());
    }

    /// <inheritdoc />
    public string Name => "AutoFix";

    /// <inheritdoc />
    public int Order => -10;

    /// <inheritdoc />
    public bool Supports(BaseItem item) => item is Movie;

    /// <inheritdoc />
    public IEnumerable<ImageType> GetSupportedImages(BaseItem item)
    {
        return new[] { ImageType.Primary, ImageType.Backdrop, ImageType.Logo };
    }

    /// <inheritdoc />
    public async Task<IEnumerable<RemoteImageInfo>> GetImages(BaseItem item, CancellationToken cancellationToken)
    {
        var list = new List<RemoteImageInfo>();

        if (Plugin.Instance?.Configuration.EnableAutoArtwork == false)
        {
            return list;
        }

        int? tmdbId = null;
        string? tmdbStr = item.GetProviderId(MetadataProvider.Tmdb);

        if (int.TryParse(tmdbStr, out var parsedId))
        {
            tmdbId = parsedId;
        }
        else
        {
            // Try resolving TMDb ID by cleaning title
            string raw = !string.IsNullOrWhiteSpace(item.Name) ? item.Name : Path.GetFileNameWithoutExtension(item.Path ?? string.Empty);
            var parsed = CleanTitleParser.Parse(raw, Plugin.Instance?.Configuration.CustomTagsToStrip);
            var results = await _tmdbClient.SearchMovieAsync(parsed.CleanTitle, parsed.Year ?? item.ProductionYear, cancellationToken).ConfigureAwait(false);
            if (results.Count > 0)
            {
                tmdbId = results[0].Id;
            }
        }

        if (!tmdbId.HasValue)
        {
            return list;
        }

        var imageResponse = await _tmdbClient.GetMovieImagesAsync(tmdbId.Value, cancellationToken).ConfigureAwait(false);
        if (imageResponse == null)
        {
            return list;
        }

        // Posters
        foreach (var poster in imageResponse.Posters.Take(5))
        {
            list.Add(new RemoteImageInfo
            {
                ProviderName = Name,
                Type = ImageType.Primary,
                Url = $"https://image.tmdb.org/t/p/original{poster.FilePath}",
                ThumbnailUrl = $"https://image.tmdb.org/t/p/w500{poster.FilePath}",
                Width = poster.Width,
                Height = poster.Height,
                CommunityRating = poster.VoteAverage
            });
        }

        // Backdrops
        foreach (var backdrop in imageResponse.Backdrops.Take(5))
        {
            list.Add(new RemoteImageInfo
            {
                ProviderName = Name,
                Type = ImageType.Backdrop,
                Url = $"https://image.tmdb.org/t/p/original{backdrop.FilePath}",
                ThumbnailUrl = $"https://image.tmdb.org/t/p/w780{backdrop.FilePath}",
                Width = backdrop.Width,
                Height = backdrop.Height,
                CommunityRating = backdrop.VoteAverage
            });
        }

        // Logos
        foreach (var logo in imageResponse.Logos.Take(3))
        {
            list.Add(new RemoteImageInfo
            {
                ProviderName = Name,
                Type = ImageType.Logo,
                Url = $"https://image.tmdb.org/t/p/original{logo.FilePath}",
                ThumbnailUrl = $"https://image.tmdb.org/t/p/w500{logo.FilePath}",
                Width = logo.Width,
                Height = logo.Height
            });
        }

        return list;
    }

    /// <inheritdoc />
    public Task<HttpResponseMessage> GetImageResponse(string url, CancellationToken cancellationToken)
    {
        var client = _httpClientFactory.CreateClient();
        return client.GetAsync(url, cancellationToken);
    }
}
