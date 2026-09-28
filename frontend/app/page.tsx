"use client";

import { useState, type DragEvent } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Result = {
  platform: string;
  goods_no: string;
  goods_name: string;
  brand_name: string;
  price: number | null;
  product_url: string;
  image_url: string;
  similarity: number;
};

type SearchResponse = {
  used_top_mask: boolean;
  top_ratio: number;
  box_preview: string;
  masked_preview: string | null;
  elapsed_ms: number;
  results: Result[];
};

async function requestSearch(file: File): Promise<SearchResponse> {
  const body = new FormData();
  body.append("image", file);
  let response: Response;
  try {
    response = await fetch(`${API}/api/search?limit=20`, { method: "POST", body });
  } catch {
    throw new Error(`검색 서버(${API})에 연결할 수 없습니다.`);
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload.detail === "string" ? payload.detail : "";
    throw new Error(`검색에 실패했습니다 (${response.status}) ${detail}`.trim());
  }
  return payload;
}

export default function Home() {
  const [original, setOriginal] = useState<string>();
  const [data, setData] = useState<SearchResponse>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [dragging, setDragging] = useState(false);

  async function search(file: File | undefined) {
    if (!file || loading) return;
    if (original) URL.revokeObjectURL(original);
    setOriginal(URL.createObjectURL(file));
    setData(undefined);
    setError(undefined);
    setLoading(true);
    try {
      setData(await requestSearch(file));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    search(event.dataTransfer.files[0]);
  }

  const status = loading
    ? "상의 영역을 찾고 임베딩을 계산하고 있습니다. 첫 검색은 모델 로딩 때문에 오래 걸릴 수 있습니다."
    : error ??
      (data &&
        [
          data.used_top_mask
            ? `상의 비율 ${(data.top_ratio * 100).toFixed(1)}%`
            : "상의를 찾지 못해 사진 전체로 검색했습니다",
          `${data.elapsed_ms.toLocaleString("ko-KR")}ms`,
          `${data.results.length}개 결과`,
        ].join(" · "));

  return (
    <main className="mx-auto w-[min(1080px,calc(100%-32px))] pt-12 pb-20">
      <h1 className="font-serif text-[clamp(32px,6vw,64px)] leading-tight font-medium">
        Find the top.
      </h1>
      <p className="mt-2 mb-7 text-muted">
        전신 사진을 올리면 상의 영역을 분리하고 등록된 상품 중 비슷한 옷을 찾습니다.
      </p>

      <label
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`flex min-h-40 cursor-pointer flex-col items-center justify-center gap-2 border border-dashed p-8 text-center transition-colors focus-within:outline-2 focus-within:outline-ink ${
          dragging ? "border-ink bg-well" : "border-line bg-card hover:bg-well/60"
        } ${loading ? "cursor-wait opacity-60" : ""}`}
      >
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="sr-only"
          disabled={loading}
          onChange={(e) => {
            search(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
        <span className="font-bold">
          {loading ? "검색 중…" : "사진을 끌어다 놓거나 클릭해서 선택하세요"}
        </span>
        <span className="text-sm text-muted">JPG · PNG · WEBP, 최대 10MB</span>
      </label>

      <p aria-live="polite" className={`mt-3.5 min-h-6 ${error ? "text-red-700" : "text-muted"}`}>
        {status}
      </p>

      {original && (
        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          <Preview label="원본" src={original} />
          <Preview label="상의 박스" src={data?.box_preview} />
          <Preview label="상의 마스크" src={data?.masked_preview ?? undefined} />
        </div>
      )}

      {data && (
        <section>
          <h2 className="mt-11 mb-4 font-serif text-3xl font-medium">검색 결과</h2>
          <div className="grid grid-cols-2 gap-3.5 md:grid-cols-4">
            {data.results.map((item) => (
              <ResultCard key={`${item.platform}-${item.goods_no}`} item={item} />
            ))}
          </div>
        </section>
      )}
    </main>
  );
}

function Preview({ label, src }: { label: string; src?: string }) {
  return (
    <figure className="relative grid h-[300px] place-items-center overflow-hidden bg-well">
      <figcaption className="absolute top-2 left-2 bg-black/70 px-2 py-1 text-xs text-white">
        {label}
      </figcaption>
      {src && <img src={src} alt={label} className="h-full w-full object-contain" />}
    </figure>
  );
}

function ResultCard({ item }: { item: Result }) {
  return (
    <a
      href={item.product_url}
      target="_blank"
      rel="noopener noreferrer"
      className="border border-line/80 bg-card transition-transform hover:-translate-y-0.5"
    >
      <img
        src={new URL(item.image_url, API).href}
        alt={item.goods_name}
        loading="lazy"
        className="aspect-[4/5] w-full bg-white object-contain"
      />
      <div className="p-3">
        <div className="text-xs text-muted">{item.brand_name || item.platform}</div>
        <div className="my-1 line-clamp-2 min-h-10 text-sm leading-snug">{item.goods_name}</div>
        <div className="font-bold">
          {item.price == null ? "가격 정보 없음" : `${item.price.toLocaleString("ko-KR")}원`}
        </div>
        <div className="text-xs text-muted">유사도 {(item.similarity * 100).toFixed(1)}%</div>
      </div>
    </a>
  );
}
