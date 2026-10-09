using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using Jellyfin.Data.Enums;
using Jellyfin.Plugin.AutoFix.Common;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.Movies;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.Providers;
using MediaBrowser.Model.Entities;
using MediaBrowser.Model.Tasks;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.AutoFix.Tasks;

/// <summary>
/// Scheduled task that scans the movie library to find items missing artwork or metadata and triggers healing.
/// </summary>
public class AutoFixLibraryScanTask : IScheduledTask
{
    private readonly ILibraryManager _libraryManager;
    private readonly IProviderManager _providerManager;
    private readonly MediaBrowser.Model.IO.IFileSystem _fileSystem;
    private readonly ILogger<AutoFixLibraryScanTask> _logger;

    public AutoFixLibraryScanTask(
        ILibraryManager libraryManager,
        IProviderManager providerManager,
        MediaBrowser.Model.IO.IFileSystem fileSystem,
        ILogger<AutoFixLibraryScanTask> logger)
    {
        _libraryManager = libraryManager;
        _providerManager = providerManager;
        _fileSystem = fileSystem;
        _logger = logger;
    }

    /// <inheritdoc />
    public string Name => "AutoFix: Heal Missing Posters & Metadata";

    /// <inheritdoc />
    public string Key => "AutoFixScanAndHeal";

    /// <inheritdoc />
    public string Description => "Scans the movie library for items missing posters or TMDb metadata, cleans their filenames, and automatically heals them.";

    /// <inheritdoc />
    public string Category => "Library";

    /// <inheritdoc />
    public IEnumerable<TaskTriggerInfo> GetDefaultTriggers()
    {
        return new[]
        {
            new TaskTriggerInfo
            {
                Type = TaskTriggerInfo.TriggerDaily,
                TimeOfDayTicks = TimeSpan.FromHours(4).Ticks
            }
        };
    }

    /// <summary>
    /// Retrieves movies from ILibraryManager dynamically to guarantee compatibility across
    /// Jellyfin 10.9, 10.10, and 12.x where the compiled return type of GetItemList changed.
    /// </summary>
    private List<Movie> GetMoviesFromLibrary()
    {
        var query = new InternalItemsQuery
        {
            IncludeItemTypes = new[] { BaseItemKind.Movie },
            Recursive = true,
            IsVirtualItem = false
        };

        try
        {
            // 1. Try GetItemList(InternalItemsQuery) via reflection
            var getItemListMethod = _libraryManager.GetType().GetMethod("GetItemList", new[] { typeof(InternalItemsQuery) });
            if (getItemListMethod != null)
            {
                var result = getItemListMethod.Invoke(_libraryManager, new object[] { query });
                if (result is IEnumerable enumerable)
                {
                    return enumerable.OfType<Movie>().ToList();
                }
            }

            // 2. Fallback: Try GetItemsResult(InternalItemsQuery)
            var getItemsResultMethod = _libraryManager.GetType().GetMethod("GetItemsResult", new[] { typeof(InternalItemsQuery) });
            if (getItemsResultMethod != null)
            {
                var queryResult = getItemsResultMethod.Invoke(_libraryManager, new object[] { query });
                var itemsProp = queryResult?.GetType().GetProperty("Items");
                if (itemsProp?.GetValue(queryResult) is IEnumerable enumerable)
                {
                    return enumerable.OfType<Movie>().ToList();
                }
            }

            // 3. Fallback: Try QueryItems(InternalItemsQuery)
            var queryItemsMethod = _libraryManager.GetType().GetMethod("QueryItems", new[] { typeof(InternalItemsQuery) });
            if (queryItemsMethod != null)
            {
                var queryResult = queryItemsMethod.Invoke(_libraryManager, new object[] { query });
                var itemsProp = queryResult?.GetType().GetProperty("Items");
                if (itemsProp?.GetValue(queryResult) is IEnumerable enumerable)
                {
                    return enumerable.OfType<Movie>().ToList();
                }
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "AutoFix: Failed to query movie items from library manager dynamically.");
        }

        return new List<Movie>();
    }

    private void QueueMovieRefresh(Movie movie)
    {
        try
        {
            var refreshOptions = new MetadataRefreshOptions(new DirectoryService(_fileSystem))
            {
                MetadataRefreshMode = MetadataRefreshMode.FullRefresh,
                ImageRefreshMode = MetadataRefreshMode.FullRefresh,
                ReplaceAllMetadata = false,
                ReplaceAllImages = false
            };

            // Try invoking QueueRefresh via reflection
            var queueMethod = _providerManager.GetType().GetMethod("QueueRefresh", new[] { typeof(Guid), typeof(MetadataRefreshOptions), typeof(RefreshPriority) });
            if (queueMethod != null)
            {
                queueMethod.Invoke(_providerManager, new object[] { movie.Id, refreshOptions, RefreshPriority.Normal });
                return;
            }

            var queueFallback = _providerManager.GetType().GetMethod("QueueRefresh", new[] { typeof(Guid), typeof(MetadataRefreshOptions) });
            if (queueFallback != null)
            {
                queueFallback.Invoke(_providerManager, new object[] { movie.Id, refreshOptions });
                return;
            }

            // Fallback: direct refresh
            _ = movie.RefreshMetadata(refreshOptions, CancellationToken.None);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "AutoFix: Failed to queue refresh for movie '{Name}'", movie.Name);
        }
    }

    /// <inheritdoc />
    public async Task ExecuteAsync(IProgress<double> progress, CancellationToken cancellationToken)
    {
        _logger.LogInformation("AutoFix: Starting library healing scan...");

        var movies = GetMoviesFromLibrary();

        if (movies.Count == 0)
        {
            _logger.LogInformation("AutoFix: No movies found in library or library query returned empty.");
            progress.Report(100.0);
            return;
        }

        int healedCount = 0;
        int total = movies.Count;

        for (int i = 0; i < total; i++)
        {
            cancellationToken.ThrowIfCancellationRequested();

            var movie = movies[i];
            bool missingPrimaryImage = !movie.HasImage(ImageType.Primary);
            bool missingTmdb = string.IsNullOrEmpty(movie.GetProviderId(MetadataProvider.Tmdb));

            // Safely rename file on disk to clean title (removes dots & release tags, NO DELETIONS)
            if (!string.IsNullOrWhiteSpace(movie.Path) && File.Exists(movie.Path))
            {
                var cfg = Plugin.Instance?.Configuration;
                if (cfg?.EnableInPlaceRenaming != false)
                {
                    TryCleanRename(movie);
                }
            }

            if (missingPrimaryImage || missingTmdb)
            {
                _logger.LogInformation("AutoFix: Healing movie '{Name}' (Missing poster: {MissingPoster}, Missing TMDb: {MissingTmdb})",
                    movie.Name, missingPrimaryImage, missingTmdb);

                QueueMovieRefresh(movie);
                healedCount++;
            }

            double percent = ((double)(i + 1) / total) * 100.0;
            progress.Report(percent);
        }

        _logger.LogInformation("AutoFix: Scan completed. Queued healing for {Count} of {Total} movies.", healedCount, total);
        progress.Report(100.0);
        await Task.CompletedTask;
    }

    private void TryCleanRename(Movie movie)
    {
        try
        {
            if (string.IsNullOrWhiteSpace(movie.Path) || !File.Exists(movie.Path))
            {
                return;
            }

            string currentPath = movie.Path;
            string fileName = Path.GetFileName(currentPath);
            var parsed = CleanTitleParser.Parse(fileName, Plugin.Instance?.Configuration.CustomTagsToStrip);

            if (!parsed.WasModified || string.IsNullOrWhiteSpace(parsed.CleanTitle))
            {
                return;
            }

            string dir = Path.GetDirectoryName(currentPath) ?? string.Empty;
            string ext = Path.GetExtension(currentPath);
            char[] invalidChars = Path.GetInvalidFileNameChars();
            string safeTitle = new string(parsed.CleanTitle.Select(c => invalidChars.Contains(c) ? '_' : c).ToArray());
            int? year = parsed.Year ?? movie.ProductionYear;
            string yearPart = year.HasValue ? $" ({year.Value})" : string.Empty;
            string newFileName = $"{safeTitle}{yearPart}{ext}";
            string newPath = Path.Combine(dir, newFileName);

            if (!string.Equals(currentPath, newPath, StringComparison.OrdinalIgnoreCase) && !File.Exists(newPath))
            {
                File.Move(currentPath, newPath);
                movie.Path = newPath;
                _logger.LogInformation("AutoFix: In-place cleanly renamed movie file on disk from '{Old}' to '{New}'", currentPath, newPath);
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "AutoFix: Could not rename movie file '{Path}'", movie.Path);
        }
    }
}
