using System;
using System.Collections.Generic;
using System.Globalization;
using Jellyfin.Plugin.AutoFix.Configuration;
using MediaBrowser.Common.Configuration;
using MediaBrowser.Common.Plugins;
using MediaBrowser.Model.Plugins;
using MediaBrowser.Model.Serialization;

namespace Jellyfin.Plugin.AutoFix;

/// <summary>
/// The main AutoFix plugin entrypoint for Jellyfin.
/// </summary>
public class Plugin : BasePlugin<PluginConfiguration>, IHasWebPages
{
    /// <summary>
    /// Initializes a new instance of the <see cref="Plugin"/> class.
    /// </summary>
    /// <param name="applicationPaths">Instance of <see cref="IApplicationPaths"/>.</param>
    /// <param name="xmlSerializer">Instance of <see cref="IXmlSerializer"/>.</param>
    public Plugin(IApplicationPaths applicationPaths, IXmlSerializer xmlSerializer)
        : base(applicationPaths, xmlSerializer)
    {
        Instance = this;
    }

    /// <inheritdoc />
    public override string Name => "AutoFix";

    /// <inheritdoc />
    public override Guid Id => Guid.Parse("d34db33f-c1e4-4d2a-89a1-55c3c0ffee01");

    /// <inheritdoc />
    public override string Description => "Automatically sanitizes messy release titles, resolves missing TMDb metadata, and injects posters so movies never appear as grey boxes.";

    /// <summary>
    /// Gets the current plugin instance.
    /// </summary>
    public static Plugin? Instance { get; private set; }

    /// <inheritdoc />
    public IEnumerable<PluginPageInfo> GetPages()
    {
        return new[]
        {
            new PluginPageInfo
            {
                Name = this.Name,
                EmbeddedResourcePath = string.Format(CultureInfo.InvariantCulture, "{0}.Web.configPage.html", GetType().Namespace),
                EnableInMainMenu = false
            }
        };
    }
}
