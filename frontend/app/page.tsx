"use client";

import { useEffect, useRef, useState, type DragEvent } from "react";

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
  const [stream, setStream] = useState<MediaStream>();
  const videoRef = useRef<HTMLVideoElement>(null);

  // Attach the live camera to <video>; stopping tracks here also covers cancel/capture/unmount.
  useEffect(() => {
    if (!stream) return;
    videoRef.current!.srcObject = stream;
    return () => stream.getTracks().forEach((track) => track.stop());
  }, [stream]);

  async function openCamera() {
    setError(undefined);
    try {
      setStream(
        await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 1920 }, height: { ideal: 1080 } },
        }),
      );
    } catch (e) {
      const name = (e as Error).name;
      setError(
        name === "NotAllowedError"
          ? "브라우저에서 카메라 권한을 허용해 주세요."
          : name === "NotFoundError"
            ? "연결된 카메라가 없습니다."
            : "카메라를 열 수 없습니다. (HTTPS 또는 localhost에서만 동작합니다)",
      );
    }
  }

  function capture() {
    const video = videoRef.current!;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")!.drawImage(video, 0, 0);
    canvas.toBlob(
      (blob) => {
        setStream(undefined);
        if (blob) search(new File([blob], "camera.jpg", { type: "image/jpeg" }));
      },
      "image/jpeg",
      0.92,
    );
  }

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
        사진을 올리거나 카메라로 찍으면 상의 영역을 분리하고 등록된 상품 중 비슷한 옷을 찾습니다.
      </p>

      {stream ? (
        <div className="relative grid place-items-center bg-black">
          {/* Mirrored like a selfie view; the captured frame keeps the real orientation. */}
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className="max-h-[70vh] w-full -scale-x-100 object-contain"
          />
          <div className="absolute inset-x-0 bottom-5 flex justify-center gap-3">
            <button
              type="button"
              onClick={capture}
              className="rounded-full bg-white px-10 py-3.5 font-bold text-ink shadow-lg focus-visible:outline-2 focus-visible:outline-white"
            >
              찰칵
            </button>
            <button
              type="button"
              onClick={() => setStream(undefined)}
              className="rounded-full bg-black/60 px-6 py-3.5 text-white focus-visible:outline-2 focus-visible:outline-white"
            >
              취소
            </button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-3 sm:flex-row">
          <label
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={`flex min-h-40 flex-1 cursor-pointer flex-col items-center justify-center gap-2 border border-dashed p-8 text-center transition-colors focus-within:outline-2 focus-within:outline-ink ${
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
          <button
            type="button"
            onClick={openCamera}
            disabled={loading}
            className="bg-ink px-8 py-4 font-bold text-white transition-opacity hover:opacity-85 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink disabled:opacity-45 sm:w-52"
          >
            카메라로 찍기
          </button>
        </div>
      )}

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
