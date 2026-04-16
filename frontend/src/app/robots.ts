import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        // Route groups like (dashboard) are invisible in URLs — use actual path segments
        disallow: [
          "/api/",
          "/dashboard/",
          "/new/",
          "/applications/",
          "/evidence/",
          "/nexus/",
          "/ats-scanner/",
          "/interview/",
          "/salary/",
          "/career/",
          "/career-analytics/",
          "/learning/",
          "/gaps/",
          "/job-board/",
          "/settings/",
          "/upload/",
          "/candidates/",
          "/builder/",
          "/export/",
          "/ab-lab/",
          "/api-keys/",
        ],
      },
    ],
    sitemap: "https://hirestack.tech/sitemap.xml",
  };
}
