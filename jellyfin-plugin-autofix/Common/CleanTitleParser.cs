using System.Text.RegularExpressions;

namespace Jellyfin.Plugin.AutoFix.Common;

/// <summary>
/// Result of parsing and sanitizing a movie filename or raw title.
/// </summary>
public record ParsedTitleInfo(string CleanTitle, int? Year, string OriginalName, bool WasModified);

/// <summary>
/// High-performance sanitizer that strips release tags, audio/video codecs,
/// website suffixes, dots, and underscores from raw filenames.
/// </summary>
public static class CleanTitleParser
{
    private static readonly Regex YearRegex = new(@"\b(19\d{2}|20\d{2})\b", RegexOptions.Compiled);

    private static readonly Regex ReleaseTagsRegex = new(
        @"\b(" +
        // Resolutions
        @"2160p|4k|uhd|1080p|720p|480p|576p|" +
        // Sources & Formats
        @"web-?dl|webrip|blu-?ray|bdrip|brrip|dvdrip|hdtv|remux|hdcam|camrip|telesync|" +
        // Video Codecs & Bit depth
        @"10bit|8bit|hevc|x264|x265|h264|h265|avc|av1|" +
        // Audio & Subtitles
        @"ddp[0-9.]*|dd[0-9.]*|dts-?hd|dts|atmos|truehd|ac3|aac|flac|dual[\s._-]?audio|multi[\s._-]?audio|hindi|english|telugu|tamil|punjabi|malayalam|kannada|esubs|subtitles|subs|" +
        // Quality / Edition tags
        @"hdr10\+?|hdr|dv|dovi|dolby[\s._-]?vision|sdr|proper|repack|extended|unrated|directors[\s._-]?cut|" +
        // Common sites and release groups
        @"moviesmod(\.[a-z0-9]+)?|bollyflix(\.[a-z0-9]+)?|hdhub4u(\.[a-z0-9]+)?|vegamovies(\.[a-z0-9]+)?|" +
        @"katmoviehd(\.[a-z0-9]+)?|yify|yts(\.[a-z0-9]+)?|rarbg|galaxyrg|psa|pahe(\.[a-z0-9]+)?|cinevood(\.[a-z0-9]+)?" +
        @")\b",
        RegexOptions.IgnoreCase | RegexOptions.Compiled
    );

    private static readonly Regex MultiSpaceRegex = new(@"\s{2,}", RegexOptions.Compiled);
    private static readonly Regex SpecialCharsRegex = new(@"[\[\](){}_.]+", RegexOptions.Compiled);

    /// <summary>
    /// Parses and sanitizes a raw filename or title into a clean title and release year.
    /// </summary>
    /// <param name="rawName">The raw input name or filename.</param>
    /// <param name="customTags">Optional extra tags to strip.</param>
    /// <returns>A <see cref="ParsedTitleInfo"/> containing the sanitized title and year.</returns>
    public static ParsedTitleInfo Parse(string rawName, string? customTags = null)
    {
        if (string.IsNullOrWhiteSpace(rawName))
        {
            return new ParsedTitleInfo(string.Empty, null, rawName ?? string.Empty, false);
        }

        string original = rawName;

        // 1. Remove file extension if present (e.g., .mkv, .mp4)
        int lastDotIndex = rawName.LastIndexOf('.');
        if (lastDotIndex > 0 && lastDotIndex > rawName.Length - 6)
        {
            string ext = rawName[lastDotIndex..].ToLowerInvariant();
            if (ext is ".mkv" or ".mp4" or ".avi" or ".mov" or ".ts" or ".m4v" or ".webm" or ".wmv")
            {
                rawName = rawName[..lastDotIndex];
            }
        }

        // 2. Locate year
        int? detectedYear = null;
        Match yearMatch = YearRegex.Match(rawName);
        string workingTitle;

        if (yearMatch.Success)
        {
            detectedYear = int.Parse(yearMatch.Value);
            // Everything before the year is our primary candidate for title
            workingTitle = rawName[..yearMatch.Index];
        }
        else
        {
            workingTitle = rawName;
        }

        // 3. Clean separators (dots, underscores, brackets, parentheses) into spaces
        workingTitle = SpecialCharsRegex.Replace(workingTitle, " ");

        // 4. Strip known release tags from workingTitle if any leaked through
        workingTitle = ReleaseTagsRegex.Replace(workingTitle, " ");

        // 5. Strip custom user tags if provided
        if (!string.IsNullOrWhiteSpace(customTags))
        {
            var tags = customTags.Split(new[] { ',', ';' }, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
            foreach (var tag in tags)
            {
                if (!string.IsNullOrWhiteSpace(tag))
                {
                    workingTitle = Regex.Replace(workingTitle, $@"\b{Regex.Escape(tag)}\b", " ", RegexOptions.IgnoreCase);
                }
            }
        }

        // 6. Clean up trailing dashes, symbols, and whitespace
        workingTitle = workingTitle.Trim(' ', '-', '_', ':', '.', '[', ']');
        workingTitle = MultiSpaceRegex.Replace(workingTitle, " ");

        // Fallback: If working title is empty after stripping (rare), return original cleaned
        if (string.IsNullOrWhiteSpace(workingTitle))
        {
            workingTitle = SpecialCharsRegex.Replace(original, " ").Trim();
            workingTitle = MultiSpaceRegex.Replace(workingTitle, " ");
        }

        bool wasModified = !string.Equals(workingTitle, original, StringComparison.Ordinal);

        return new ParsedTitleInfo(workingTitle, detectedYear, original, wasModified);
    }
}
