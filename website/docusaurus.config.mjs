const repository = "https://github.com/psyb0t/docker-audiolla";
const baseUrl = "/docker-audiolla/";
const hasOpenAPI = true;

export default {
  title: "audiolla",
  tagline: "Audio editing, analysis and generation",
  url: "https://psyb0t.github.io",
  baseUrl,
  trailingSlash: true,
  future: { faster: { rspackBundler: true, swcJsLoader: true } },
  organizationName: "psyb0t",
  projectName: "docker-audiolla",
  onBrokenLinks: "throw",
  markdown: { format: "detect", hooks: { onBrokenMarkdownLinks: "throw" } },
  staticDirectories: [".assets"],
  scripts: [{ src: "https://psyb0t.github.io/analytics.js", async: true }],
  presets: [
    ["classic", {
      blog: false,
      sitemap: { ignorePatterns: [baseUrl + "search", baseUrl + "search/"] },
      theme: { customCss: "./src/css/theme.css" },
      docs: {
        path: ".content",
        routeBasePath: "/",
        sidebarPath: "./sidebars.mjs",
        ...(hasOpenAPI ? { docItemComponent: "@theme/ApiItem" } : {}),
        editUrl: ({ docPath }) => docPath.startsWith("reference/")
          ? undefined
          : repository + "/edit/main/docs/" + docPath,
      },
    }],
  ],
  plugins: hasOpenAPI ? [["docusaurus-plugin-openapi-docs", {
    id: "api",
    docsPluginId: "classic",
    config: {
      reference: {
        specPath: ".assets/reference/openapi.yaml",
        outputDir: ".content/reference",
        showInfoPage: false,
        hideSendButton: true,
        sidebarOptions: { groupPathsBy: "tag" },
      },
    },
  }]] : [],
  themes: [
    ...(hasOpenAPI ? ["docusaurus-theme-openapi-docs"] : []),
    ["@easyops-cn/docusaurus-search-local", {
      docsDir: ".content",
      docsRouteBasePath: "/",
      indexBlog: false,
      hashed: true,
    }],
  ],
  themeConfig: {
    navbar: {
      title: "audiolla",
      items: [
        { href: "https://psyb0t.github.io/projects/", label: "All projects", position: "left" },
        { href: repository, label: "GitHub", position: "right" },
        { href: repository + "/blob/main/CHANGELOG.md", label: "Changelog", position: "right" },
      ],
    },
    colorMode: { defaultMode: "dark" },
  },
};
