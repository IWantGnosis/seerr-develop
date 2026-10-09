using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
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

    /// <inheritdoc />
    public async Task ExecuteAsync(IProgress<double> progress, CancellationToken cancellationToken)
    {
        _logger.LogInformation("AutoFix: Starting library healing scan...");

        var movies = _libraryManager.GetItemList(new InternalItemsQuery
        {
            IncludeItemTypes = new[] { BaseItemKind.Movie },
            Recursive = true,
            IsVirtualItem = false
        }).OfType<Movie>().ToList();

        if (movies.Count == 0)
        {
            _logger.LogInformation("AutoFix: No movies found in library.");
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

            if (missingPrimaryImage || missingTmdb)
            {
                _logger.LogInformation("AutoFix: Healing movie '{Name}' (Missing poster: {MissingPoster}, Missing TMDb: {MissingTmdb})",
                    movie.Name, missingPrimaryImage, missingTmdb);

                // Queue a refresh with Jellyfin's provider manager
                _providerManager.QueueRefresh(movie.Id, new MetadataRefreshOptions(new DirectoryService(_fileSystem))
                {
                    MetadataRefreshMode = MetadataRefreshMode.FullRefresh,
                    ImageRefreshMode = MetadataRefreshMode.FullRefresh,
                    ReplaceAllMetadata = false,
                    ReplaceAllImages = false
                }, RefreshPriority.Normal);

                healedCount++;
            }

            double percent = ((double)(i + 1) / total) * 100.0;
            progress.Report(percent);
        }

        _logger.LogInformation("AutoFix: Scan completed. Queued healing for {Count} of {Total} movies.", healedCount, total);
        progress.Report(100.0);
        await Task.CompletedTask;
    }
}
