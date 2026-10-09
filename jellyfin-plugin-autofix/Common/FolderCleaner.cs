using System;
using System.IO;
using System.Linq;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.AutoFix.Common;

/// <summary>
/// Handles automatic folder maintenance, junk file elimination, and duplicate movie cleanup.
/// </summary>
public static class FolderCleaner
{
    private static readonly string[] JunkExtensions = new[]
    {
        ".txt", ".url", ".nfo", ".exe", ".bat", ".cmd", ".lnk",
        ".torrent", ".part", ".crdownload", ".html", ".htm", ".website"
    };

    private static readonly string[] VideoExtensions = new[]
    {
        ".mkv", ".mp4", ".avi", ".mov", ".ts", ".m4v", ".webm"
    };

    /// <summary>
    /// Cleans junk files, sample clips, and older duplicate versions from a movie's directory.
    /// </summary>
    /// <param name="folderPath">The directory containing the movie.</param>
    /// <param name="newMovieFilePath">The path of the newly added movie file.</param>
    /// <param name="removeJunk">Whether to remove junk/sample files.</param>
    /// <param name="removeDuplicates">Whether to remove duplicate movie files in the folder.</param>
    /// <param name="logger">Logger instance.</param>
    public static void CleanMovieFolder(
        string folderPath,
        string? newMovieFilePath,
        bool removeJunk,
        bool removeDuplicates,
        ILogger logger)
    {
        if (string.IsNullOrWhiteSpace(folderPath) || !Directory.Exists(folderPath))
        {
            return;
        }

        try
        {
            var dirInfo = new DirectoryInfo(folderPath);

            // 1. Remove Junk files and sample clips
            if (removeJunk)
            {
                foreach (var file in dirInfo.GetFiles("*", SearchOption.AllDirectories))
                {
                    // Check junk extension
                    if (JunkExtensions.Contains(file.Extension, StringComparer.OrdinalIgnoreCase))
                    {
                        try
                        {
                            file.Delete();
                            logger.LogInformation("AutoFix FolderCleaner: Deleted junk file '{Path}'", file.FullName);
                        }
                        catch (Exception ex)
                        {
                            logger.LogWarning(ex, "AutoFix FolderCleaner: Could not delete junk file '{Path}'", file.FullName);
                        }
                        continue;
                    }

                    // Check sample clips (files containing 'sample' and under 75 MB)
                    if (VideoExtensions.Contains(file.Extension, StringComparer.OrdinalIgnoreCase)
                        && file.Name.IndexOf("sample", StringComparison.OrdinalIgnoreCase) >= 0
                        && file.Length < 75 * 1024 * 1024)
                    {
                        try
                        {
                            file.Delete();
                            logger.LogInformation("AutoFix FolderCleaner: Deleted sample clip '{Path}'", file.FullName);
                        }
                        catch (Exception ex)
                        {
                            logger.LogWarning(ex, "AutoFix FolderCleaner: Could not delete sample clip '{Path}'", file.FullName);
                        }
                    }
                }
            }

            // 2. Remove duplicate movie files in the same folder if a newer/better movie file was added
            if (removeDuplicates && !string.IsNullOrWhiteSpace(newMovieFilePath) && File.Exists(newMovieFilePath))
            {
                var newFileInfo = new FileInfo(newMovieFilePath);
                var allVideos = dirInfo.GetFiles("*", SearchOption.TopDirectoryOnly)
                    .Where(f => VideoExtensions.Contains(f.Extension, StringComparer.OrdinalIgnoreCase))
                    .Where(f => !string.Equals(f.FullName, newFileInfo.FullName, StringComparison.OrdinalIgnoreCase))
                    .Where(f => f.Length > 100 * 1024 * 1024) // Must be larger than 100MB to be a movie file
                    .ToList();

                foreach (var oldVideo in allVideos)
                {
                    try
                    {
                        // If new movie file is significantly larger or same title, remove old file
                        oldVideo.Delete();
                        logger.LogInformation("AutoFix FolderCleaner: Removed old/duplicate movie version '{Old}' in favor of '{New}'",
                            oldVideo.FullName, newFileInfo.FullName);
                    }
                    catch (Exception ex)
                    {
                        logger.LogWarning(ex, "AutoFix FolderCleaner: Could not remove duplicate file '{Path}'", oldVideo.FullName);
                    }
                }
            }

            // 3. Remove leftover empty subdirectories
            foreach (var subDir in dirInfo.GetDirectories("*", SearchOption.AllDirectories))
            {
                try
                {
                    if (Directory.Exists(subDir.FullName) && !subDir.EnumerateFileSystemInfos().Any())
                    {
                        subDir.Delete();
                        logger.LogInformation("AutoFix FolderCleaner: Deleted empty subdirectory '{Path}'", subDir.FullName);
                    }
                }
                catch
                {
                    // Ignore non-empty or permission errors
                }
            }
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "AutoFix FolderCleaner: Error during folder cleanup of '{Folder}'", folderPath);
        }
    }
}
