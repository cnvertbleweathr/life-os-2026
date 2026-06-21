"use client";

import { useEffect, useState } from "react";
import { musicApi } from "@/lib/api";
import { Card, PageHeader, SectionLabel, Empty, Loading } from "@/components/ui/primitives";

export default function MusicPage() {
  const [topArtists, setTopArtists] = useState<unknown[] | null>(null);
  const [news, setNews]             = useState<unknown[] | null>(null);

  useEffect(() => {
    musicApi.topArtists().then(setTopArtists).catch(() => setTopArtists([]));
    musicApi.news().then(setNews).catch(() => setNews([]));
  }, []);

  return (
    <div>
      <PageHeader title="Music" sub="via Spotify" />
      <div className="p-6 grid grid-cols-2 gap-4">
        <Card>
          <SectionLabel>Top artists</SectionLabel>
          {topArtists === null ? (
            <Loading />
          ) : topArtists.length === 0 ? (
            <Empty
              message="No data yet."
              detail="May need a current-year row in streams_clean.csv — worth checking the pipeline."
            />
          ) : (
            <pre className="text-2xs text-muted">{JSON.stringify(topArtists, null, 2)}</pre>
          )}
        </Card>

        <Card>
          <SectionLabel>Music news</SectionLabel>
          {news === null ? (
            <Loading />
          ) : news.length === 0 ? (
            <Empty
              message="Not configured."
              detail="NEWS_API_KEY isn't set in .env — expected, not a bug."
            />
          ) : (
            <pre className="text-2xs text-muted">{JSON.stringify(news, null, 2)}</pre>
          )}
        </Card>
      </div>
    </div>
  );
}
