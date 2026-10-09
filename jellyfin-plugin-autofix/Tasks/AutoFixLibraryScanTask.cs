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
using MediaBrowser.Controller.Entities.TV;
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

    private List<Episode> GetEpisodesFromLibrary()
    {
        var query = new InternalItemsQuery
        {
            IncludeItemTypes = new[] { BaseItemKind.Episode },
            Recursive = true,
            IsVirtualItem = false
        };

        try
        {
            var getItemListMethod = _libraryManager.GetType().GetMethod("GetItemList", new[] { typeof(InternalItemsQuery) });
            if (getItemListMethod != null)
            {
                var result = getItemListMethod.Invoke(_libraryManager, new object[] { query });
                if (result is IEnumerable enumerable)
                {
                    return enumerable.OfType<Episode>().ToList();
                }
            }

            var getItemsResultMethod = _libraryManager.GetType().GetMethod("GetItemsResult", new[] { typeof(InternalItemsQuery) });
            if (getItemsResultMethod != null)
            {
                var queryResult = getItemsResultMethod.Invoke(_libraryManager, new object[] { query });
                var itemsProp = queryResult?.GetType().GetProperty("Items");
                if (itemsProp?.GetValue(queryResult) is IEnumerable enumerable)
                {
                    return enumerable.OfType<Episode>().ToList();
                }
            }

            var queryItemsMethod = _libraryManager.GetType().GetMethod("QueryItems", new[] { typeof(InternalItemsQuery) });
            if (queryItemsMethod != null)
            {
                var queryResult = queryItemsMethod.Invoke(_libraryManager, new object[] { query });
                var itemsProp = queryResult?.GetType().GetProperty("Items");
                if (itemsProp?.GetValue(queryResult) is IEnumerable enumerable)
                {
                    return enumerable.OfType<Episode>().ToList();
                }
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "AutoFix: Failed to query episode items from library manager dynamically.");
        }

        return new List<Episode>();
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
        _logger.LogInformation("AutoFix: Starting library healing and in-place renaming scan...");

        var movies = GetMoviesFromLibrary();
        var episodes = GetEpisodesFromLibrary();

        int totalItems = movies.Count + episodes.Count;
        if (totalItems == 0)
        {
            _logger.LogInformation("AutoFix: No movies or episodes found in library or library query returned empty.");
            progress.Report(100.0);
            return;
        }

        int healedCount = 0;
        int processedCount = 0;
        var cfg = Plugin.Instance?.Configuration;
        bool inPlaceRenaming = cfg?.EnableInPlaceRenaming != false;

        // 1. Process Movies
        for (int i = 0; i < movies.Count; i++)
        {
            cancellationToken.ThrowIfCancellationRequested();

            var movie = movies[i];
            bool missingPrimaryImage = !movie.HasImage(ImageType.Primary);
            bool missingTmdb = string.IsNullOrEmpty(movie.GetProviderId(MetadataProvider.Tmdb));

            if (inPlaceRenaming && !string.IsNullOrWhiteSpace(movie.Path))
            {
                TryCleanRename(movie);
            }

            if (missingPrimaryImage || missingTmdb)
            {
                _logger.LogInformation("AutoFix: Healing movie '{Name}' (Missing poster: {MissingPoster}, Missing TMDb: {MissingTmdb})",
                    movie.Name, missingPrimaryImage, missingTmdb);

                QueueMovieRefresh(movie);
                healedCount++;
            }

            processedCount++;
            double percent = ((double)processedCount / totalItems) * 100.0;
            progress.Report(percent);
        }

        // 2. Process TV Episodes
        for (int i = 0; i < episodes.Count; i++)
        {
            cancellationToken.ThrowIfCancellationRequested();

            var episode = episodes[i];
            if (inPlaceRenaming && !string.IsNullOrWhiteSpace(episode.Path))
            {
                TryCleanRenameEpisode(episode);
            }

            processedCount++;
            double percent = ((double)processedCount / totalItems) * 100.0;
            progress.Report(percent);
        }

        _logger.LogInformation("AutoFix: Scan completed. Processed {MoviesCount} movies and {EpisodesCount} episodes.",
            movies.Count, episodes.Count);
        progress.Report(100.0);
        await Task.CompletedTask;
    }

    private void TryCleanRename(Movie movie)
    {
        try
        {
            if (string.IsNullOrWhiteSpace(movie.Path))
            {
                return;
            }

            // 1. Resolve video file path (whether movie.Path points to a file or a folder)
            string? currentVideoFile = null;
            if (File.Exists(movie.Path))
            {
                currentVideoFile = movie.Path;
            }
            else if (Directory.Exists(movie.Path))
            {
                var videoExtensions = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
                {
                    ".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".webm", ".wmv"
                };
                currentVideoFile = Directory.GetFiles(movie.Path)
                    .FirstOrDefault(f => videoExtensions.Contains(Path.GetExtension(f)));
            }

            if (string.IsNullOrWhiteSpace(currentVideoFile) || !File.Exists(currentVideoFile))
            {
                _logger.LogDebug("AutoFix: No video file found for movie '{Name}' at '{Path}'", movie.Name, movie.Path);
                return;
            }

            // 2. Use confirmed Jellyfin metadata (Title and ProductionYear) as the source of truth
            string confirmedTitle = !string.IsNullOrWhiteSpace(movie.Name) ? movie.Name : string.Empty;
            int? confirmedYear = movie.ProductionYear;

            // Fallback to title parser if movie.Name is empty
            if (string.IsNullOrWhiteSpace(confirmedTitle))
            {
                string rawFileName = Path.GetFileName(currentVideoFile);
                var parsed = CleanTitleParser.Parse(rawFileName, Plugin.Instance?.Configuration.CustomTagsToStrip);
                confirmedTitle = parsed.CleanTitle;
                confirmedYear ??= parsed.Year;
            }

            if (string.IsNullOrWhiteSpace(confirmedTitle))
            {
                return;
            }

            // 3. Sanitize filesystem invalid characters (: / \ * ? " < > |) into clean spaces/dashes
            char[] invalidChars = Path.GetInvalidFileNameChars();
            string safeTitle = new string(confirmedTitle.Select(c => invalidChars.Contains(c) ? ' ' : c).ToArray()).Trim();
            safeTitle = System.Text.RegularExpressions.Regex.Replace(safeTitle, @"\s+", " ");

            string yearPart = confirmedYear.HasValue && confirmedYear.Value > 1900 ? $" ({confirmedYear.Value})" : string.Empty;
            string targetBaseName = $"{safeTitle}{yearPart}".Trim();

            string dir = Path.GetDirectoryName(currentVideoFile) ?? string.Empty;
            string ext = Path.GetExtension(currentVideoFile);
            string currentBaseName = Path.GetFileNameWithoutExtension(currentVideoFile);
            string newFileName = $"{targetBaseName}{ext}";
            string newPath = Path.Combine(dir, newFileName);

            // 4. Compare: if file is already cleanly named, skip
            if (string.Equals(currentBaseName, targetBaseName, StringComparison.OrdinalIgnoreCase))
            {
                _logger.LogInformation("AutoFix: Movie '{Name}' is already cleanly named: '{File}'", movie.Name, Path.GetFileName(currentVideoFile));
                return;
            }

            // 5. Safely rename the file and companion subtitles (NO DELETIONS)
            if (!File.Exists(newPath))
            {
                File.Move(currentVideoFile, newPath);
                if (string.Equals(movie.Path, currentVideoFile, StringComparison.OrdinalIgnoreCase))
                {
                    movie.Path = newPath;
                }

                _logger.LogInformation("AutoFix: In-place cleanly renamed movie file from '{Old}' to '{New}' (Confirmed Jellyfin metadata)", currentVideoFile, newPath);

                // Also rename matching companion subtitle files (.srt, .vtt, etc.)
                RenameCompanionSubtitleFiles(dir, currentBaseName, targetBaseName);
            }
            else
            {
                _logger.LogWarning("AutoFix: Cannot rename '{Old}' because target '{New}' already exists on disk.", currentVideoFile, newPath);
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "AutoFix: Failed to rename movie file for '{Name}' at '{Path}'. (Check Linux write permissions for 'jellyfin' user)", movie.Name, movie.Path);
        }
    }

    private void TryCleanRenameEpisode(Episode episode)
    {
        try
        {
            if (string.IsNullOrWhiteSpace(episode.Path))
            {
                return;
            }

            string? currentVideoFile = null;
            if (File.Exists(episode.Path))
            {
                currentVideoFile = episode.Path;
            }
            else if (Directory.Exists(episode.Path))
            {
                var videoExtensions = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
                {
                    ".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".webm", ".wmv"
                };
                currentVideoFile = Directory.GetFiles(episode.Path)
                    .FirstOrDefault(f => videoExtensions.Contains(Path.GetExtension(f)));
            }

            if (string.IsNullOrWhiteSpace(currentVideoFile) || !File.Exists(currentVideoFile))
            {
                return;
            }

            // 1. Get Series name
            string seriesName = !string.IsNullOrWhiteSpace(episode.SeriesName)
                ? episode.SeriesName
                : (episode.Series?.Name ?? string.Empty);

            if (string.IsNullOrWhiteSpace(seriesName))
            {
                var seasonDir = Path.GetDirectoryName(currentVideoFile);
                var showDir = Path.GetDirectoryName(seasonDir);
                seriesName = Path.GetFileName(showDir) ?? string.Empty;
            }

            int seasonNumber = episode.ParentIndexNumber ?? 1;
            int episodeNumber = episode.IndexNumber ?? 1;
            string episodeTitle = !string.IsNullOrWhiteSpace(episode.Name) ? episode.Name : string.Empty;

            // 2. Sanitize series name and title
            char[] invalidChars = Path.GetInvalidFileNameChars();
            string safeSeries = new string(seriesName.Select(c => invalidChars.Contains(c) ? ' ' : c).ToArray()).Trim();
            safeSeries = System.Text.RegularExpressions.Regex.Replace(safeSeries, @"\s+", " ");

            string safeTitle = new string(episodeTitle.Select(c => invalidChars.Contains(c) ? ' ' : c).ToArray()).Trim();
            safeTitle = System.Text.RegularExpressions.Regex.Replace(safeTitle, @"\s+", " ");

            bool isGenericTitle = string.IsNullOrWhiteSpace(safeTitle)
                || safeTitle.Equals($"Episode {episodeNumber}", StringComparison.OrdinalIgnoreCase)
                || safeTitle.Equals($"Episode {episodeNumber:D2}", StringComparison.OrdinalIgnoreCase);

            string targetBaseName = isGenericTitle
                ? $"{safeSeries} - S{seasonNumber:D2}E{episodeNumber:D2}".Trim(' ', '-')
                : $"{safeSeries} - S{seasonNumber:D2}E{episodeNumber:D2} - {safeTitle}".Trim(' ', '-');

            string dir = Path.GetDirectoryName(currentVideoFile) ?? string.Empty;
            string ext = Path.GetExtension(currentVideoFile);
            string currentBaseName = Path.GetFileNameWithoutExtension(currentVideoFile);
            string newFileName = $"{targetBaseName}{ext}";
            string newPath = Path.Combine(dir, newFileName);

            // 3. Skip if already cleanly named
            if (string.Equals(currentBaseName, targetBaseName, StringComparison.OrdinalIgnoreCase))
            {
                _logger.LogInformation("AutoFix: Episode '{Series} S{Season:D2}E{Ep:D2}' is already cleanly named: '{File}'",
                    seriesName, seasonNumber, episodeNumber, Path.GetFileName(currentVideoFile));
                return;
            }

            // 4. Safely rename file and companion subtitles (NO DELETIONS)
            if (!File.Exists(newPath))
            {
                File.Move(currentVideoFile, newPath);
                if (string.Equals(episode.Path, currentVideoFile, StringComparison.OrdinalIgnoreCase))
                {
                    episode.Path = newPath;
                }

                _logger.LogInformation("AutoFix: In-place cleanly renamed episode file from '{Old}' to '{New}' (Confirmed Jellyfin metadata)",
                    currentVideoFile, newPath);

                RenameCompanionSubtitleFiles(dir, currentBaseName, targetBaseName);
            }
            else
            {
                _logger.LogWarning("AutoFix: Cannot rename '{Old}' because target '{New}' already exists on disk.", currentVideoFile, newPath);
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "AutoFix: Failed to rename episode file at '{Path}'", episode.Path);
        }
    }

    private void RenameCompanionSubtitleFiles(string dir, string oldBaseName, string newBaseName)
    {
        try
        {
            var subtitleExts = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { ".srt", ".vtt", ".sub", ".idx", ".smi", ".ass", ".ssa" };
            var files = Directory.GetFiles(dir);
            foreach (var file in files)
            {
                string ext = Path.GetExtension(file);
                if (!subtitleExts.Contains(ext))
                {
                    continue;
                }

                string nameWithoutExt = Path.GetFileNameWithoutExtension(file);
                if (nameWithoutExt.StartsWith(oldBaseName, StringComparison.OrdinalIgnoreCase))
                {
                    string suffix = nameWithoutExt.Substring(oldBaseName.Length);
                    string newSubName = $"{newBaseName}{suffix}{ext}";
                    string newSubPath = Path.Combine(dir, newSubName);
                    if (!string.Equals(file, newSubPath, StringComparison.OrdinalIgnoreCase) && !File.Exists(newSubPath))
                    {
                        File.Move(file, newSubPath);
                        _logger.LogInformation("AutoFix: In-place cleanly renamed subtitle file from '{Old}' to '{New}'", file, newSubPath);
                    }
                }
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "AutoFix: Failed to rename companion subtitle files in '{Dir}'", dir);
        }
    }
}
