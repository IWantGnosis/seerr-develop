using MediaBrowser.Model.Plugins;

namespace Jellyfin.Plugin.AutoFix.Configuration;

/// <summary>
/// Configuration options for the AutoFix plugin.
/// </summary>
public class PluginConfiguration : BasePluginConfiguration
{
    /// <summary>
    /// Gets or sets a value indicating whether to sanitize messy filenames before searching.
    /// </summary>
    public bool EnableSanitizer { get; set; } = true;

    /// <summary>
    /// Gets or sets a value indicating whether to use multi-tier fuzzy matching if exact search fails.
    /// </summary>
    public bool EnableFuzzyMatcher { get; set; } = true;

    /// <summary>
    /// Gets or sets a value indicating whether to automatically fetch and inject posters and backdrops.
    /// </summary>
    public bool EnableAutoArtwork { get; set; } = true;

    /// <summary>
    /// Gets or sets a value indicating whether to rename files in-place on disk to standard naming.
    /// </summary>
    public bool EnableInPlaceRenaming { get; set; } = false;

    /// <summary>
    /// Gets or sets a custom TMDb API key. If empty, a built-in fallback key is used.
    /// </summary>
    public string TmdbApiKey { get; set; } = string.Empty;

    /// <summary>
    /// Gets or sets a value indicating whether to clean junk files (.txt, .url, .nfo, sample clips) in movie folders.
    /// </summary>
    public bool EnableFolderCleaner { get; set; } = true;

    /// <summary>
    /// Gets or sets a value indicating whether to remove older duplicate versions of a movie when a new version is added.
    /// </summary>
    public bool EnableDuplicateCleaner { get; set; } = true;

    /// <summary>
    /// Gets or sets comma-separated custom release tags to strip.
    /// </summary>
    public string CustomTagsToStrip { get; set; } = "moviesmod,bollyflix,hdhub4u,vegamovies,katmoviehd,pahe,yts,yify,psa,rarbg,galaxyrg,1080p,720p,2160p,4k,10bit,hevc,x264,x265,web-dl,bluray";
}
