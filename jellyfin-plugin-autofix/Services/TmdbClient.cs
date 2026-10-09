using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Http;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.AutoFix.Services;

public class TmdbMovieSearchResult
{
    [JsonPropertyName("id")]
    public int Id { get; set; }

    [JsonPropertyName("title")]
    public string Title { get; set; } = string.Empty;

    [JsonPropertyName("original_title")]
    public string? OriginalTitle { get; set; }

    [JsonPropertyName("overview")]
    public string? Overview { get; set; }

    [JsonPropertyName("release_date")]
    public string? ReleaseDate { get; set; }

    [JsonPropertyName("poster_path")]
    public string? PosterPath { get; set; }

    [JsonPropertyName("backdrop_path")]
    public string? BackdropPath { get; set; }

    [JsonPropertyName("vote_average")]
    public float VoteAverage { get; set; }
}

public class TmdbSearchResponse
{
    [JsonPropertyName("page")]
    public int Page { get; set; }

    [JsonPropertyName("results")]
    public List<TmdbMovieSearchResult> Results { get; set; } = new();
}

public class TmdbImageItem
{
    [JsonPropertyName("file_path")]
    public string FilePath { get; set; } = string.Empty;

    [JsonPropertyName("width")]
    public int Width { get; set; }

    [JsonPropertyName("height")]
    public int Height { get; set; }

    [JsonPropertyName("vote_average")]
    public float VoteAverage { get; set; }
}

public class TmdbImagesResponse
{
    [JsonPropertyName("id")]
    public int Id { get; set; }

    [JsonPropertyName("posters")]
    public List<TmdbImageItem> Posters { get; set; } = new();

    [JsonPropertyName("backdrops")]
    public List<TmdbImageItem> Backdrops { get; set; } = new();

    [JsonPropertyName("logos")]
    public List<TmdbImageItem> Logos { get; set; } = new();
}

public class TmdbMovieDetails : TmdbMovieSearchResult
{
    [JsonPropertyName("imdb_id")]
    public string? ImdbId { get; set; }
}

/// <summary>
/// Client for querying The Movie Database (TMDb) API.
/// </summary>
public class TmdbClient
{
    private const string DefaultApiKey = "4f38948b43849fbe5f595bc68d304a42";
    private const string BaseUrl = "https://api.themoviedb.org/3";
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly ILogger<TmdbClient> _logger;

    public TmdbClient(IHttpClientFactory httpClientFactory, ILogger<TmdbClient> logger)
    {
        _httpClientFactory = httpClientFactory;
        _logger = logger;
    }

    private string GetApiKey()
    {
        var configKey = Plugin.Instance?.Configuration.TmdbApiKey;
        return !string.IsNullOrWhiteSpace(configKey) ? configKey.Trim() : DefaultApiKey;
    }

    private HttpClient CreateClient()
    {
        var client = _httpClientFactory.CreateClient();
        client.Timeout = TimeSpan.FromSeconds(15);
        return client;
    }

    /// <summary>
    /// Searches for movies using clean title and optional release year.
    /// </summary>
    public async Task<List<TmdbMovieSearchResult>> SearchMovieAsync(string query, int? year, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(query))
        {
            return new List<TmdbMovieSearchResult>();
        }

        string apiKey = GetApiKey();
        var client = CreateClient();

        // 1. First attempt: search with year if available
        if (year.HasValue && year.Value > 1900)
        {
            string urlWithYear = $"{BaseUrl}/search/movie?api_key={apiKey}&query={Uri.EscapeDataString(query)}&year={year.Value}&include_adult=false";
            try
            {
                var response = await client.GetAsync(urlWithYear, cancellationToken).ConfigureAwait(false);
                if (response.IsSuccessStatusCode)
                {
                    using var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
                    var data = await JsonSerializer.DeserializeAsync<TmdbSearchResponse>(stream, cancellationToken: cancellationToken).ConfigureAwait(false);
                    if (data?.Results != null && data.Results.Count > 0)
                    {
                        return data.Results;
                    }
                }
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "AutoFix: Search with year failed for '{Query}' ({Year})", query, year);
            }
        }

        // 2. Second attempt: search without year
        string urlWithoutYear = $"{BaseUrl}/search/movie?api_key={apiKey}&query={Uri.EscapeDataString(query)}&include_adult=false";
        try
        {
            var response = await client.GetAsync(urlWithoutYear, cancellationToken).ConfigureAwait(false);
            if (response.IsSuccessStatusCode)
            {
                using var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
                var data = await JsonSerializer.DeserializeAsync<TmdbSearchResponse>(stream, cancellationToken: cancellationToken).ConfigureAwait(false);
                if (data?.Results != null && data.Results.Count > 0)
                {
                    return data.Results;
                }
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "AutoFix: Search without year failed for '{Query}'", query);
        }

        // 3. Third attempt (Fuzzy Franchise root fallback):
        // If query has colons, subtitles, or multiple parts (e.g. "Minions and Monsters"), try root phrase if > 2 words
        if (Plugin.Instance?.Configuration.EnableFuzzyMatcher == true)
        {
            var words = query.Split(' ', StringSplitOptions.RemoveEmptyEntries);
            if (words.Length >= 3)
            {
                string shortened = $"{words[0]} {words[1]}";
                string fallbackUrl = $"{BaseUrl}/search/movie?api_key={apiKey}&query={Uri.EscapeDataString(shortened)}&include_adult=false";
                try
                {
                    var response = await client.GetAsync(fallbackUrl, cancellationToken).ConfigureAwait(false);
                    if (response.IsSuccessStatusCode)
                    {
                        using var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
                        var data = await JsonSerializer.DeserializeAsync<TmdbSearchResponse>(stream, cancellationToken: cancellationToken).ConfigureAwait(false);
                        if (data?.Results != null && data.Results.Count > 0)
                        {
                            return data.Results;
                        }
                    }
                }
                catch (Exception ex)
                {
                    _logger.LogDebug(ex, "AutoFix: Fuzzy root search failed for '{Shortened}'", shortened);
                }
            }
        }

        return new List<TmdbMovieSearchResult>();
    }

    /// <summary>
    /// Gets full details for a movie by TMDb ID.
    /// </summary>
    public async Task<TmdbMovieDetails?> GetMovieDetailsAsync(int tmdbId, CancellationToken cancellationToken)
    {
        string apiKey = GetApiKey();
        var client = CreateClient();
        string url = $"{BaseUrl}/movie/{tmdbId}?api_key={apiKey}&append_to_response=external_ids";

        try
        {
            var response = await client.GetAsync(url, cancellationToken).ConfigureAwait(false);
            if (response.IsSuccessStatusCode)
            {
                using var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
                return await JsonSerializer.DeserializeAsync<TmdbMovieDetails>(stream, cancellationToken: cancellationToken).ConfigureAwait(false);
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "AutoFix: Failed to get movie details for TMDb ID {TmdbId}", tmdbId);
        }

        return null;
    }

    /// <summary>
    /// Gets images (posters, backdrops, logos) for a movie by TMDb ID.
    /// </summary>
    public async Task<TmdbImagesResponse?> GetMovieImagesAsync(int tmdbId, CancellationToken cancellationToken)
    {
        string apiKey = GetApiKey();
        var client = CreateClient();
        string url = $"{BaseUrl}/movie/{tmdbId}/images?api_key={apiKey}&include_image_language=en,null";

        try
        {
            var response = await client.GetAsync(url, cancellationToken).ConfigureAwait(false);
            if (response.IsSuccessStatusCode)
            {
                using var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
                return await JsonSerializer.DeserializeAsync<TmdbImagesResponse>(stream, cancellationToken: cancellationToken).ConfigureAwait(false);
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "AutoFix: Failed to fetch images for TMDb ID {TmdbId}", tmdbId);
        }

        return null;
    }
}
