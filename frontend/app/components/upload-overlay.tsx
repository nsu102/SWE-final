"use client";

import { ChangeEvent, DragEvent, useEffect, useRef, useState } from "react";

type Props = { inert: boolean; onClose: () => void; onFile: (file?: File, label?: string) => void; onError: (message: string) => void };

export default function UploadOverlay({ inert, onClose, onFile, onError }: Props) {
  const [closing, setClosing] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [stream, setStream] = useState<MediaStream>();
  const videoRef = useRef<HTMLVideoElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (closeTimer.current) clearTimeout(closeTimer.current); }, []);

  // Attach the live camera to <video>; stopping tracks here also covers cancel/capture/unmount.
  useEffect(() => {
    if (!stream) return;
    videoRef.current!.srcObject = stream;
    return () => stream.getTracks().forEach(track => track.stop());
  }, [stream]);

  function close() {
    if (closing) return;
    setStream(undefined);
    setClosing(true);
    closeTimer.current = setTimeout(onClose, 650);
  }

  function choose(event: ChangeEvent<HTMLInputElement>) {
    onFile(event.target.files?.[0]);
    event.target.value = "";
  }

  function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    onFile(event.dataTransfer.files?.[0]);
  }

  async function openCamera() {
    try {
      setStream(await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1080 } } }));
    } catch (error) {
      const name = (error as Error).name;
      onError(name === "NotAllowedError" ? "브라우저에서 카메라 권한을 허용해 주세요."
        : name === "NotFoundError" ? "연결된 카메라가 없어요."
        : "카메라를 열 수 없어요. (HTTPS 또는 localhost에서만 동작해요)");
    }
  }

  function capture() {
    const video = videoRef.current!;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")!.drawImage(video, 0, 0);
    canvas.toBlob(blob => { if (blob) onFile(new File([blob], "camera.jpg", { type: "image/jpeg" }), "카메라 촬영"); }, "image/jpeg", 0.92);
  }

  return <section className={closing ? "upload-mode closing" : "upload-mode"} inert={inert} aria-hidden={inert || undefined} aria-modal={!inert} role="dialog">
    <input ref={fileInput} className="file-input" type="file" accept="image/jpeg,image/png,image/webp" onChange={choose} />
    <button className="close-upload" onClick={close} aria-label="업로드 화면 닫기">×</button>
    <div className="upload-content">
      <h2>UPLOAD PHOTO</h2>
      <div className={dragging ? "upload-finder dragging" : "upload-finder"} onDragOver={event => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={drop}>
        <span className="finder-corner top-left" /><span className="finder-corner top-right" /><span className="finder-corner bottom-left" /><span className="finder-corner bottom-right" />
        {stream ? <>
          <video ref={videoRef} autoPlay playsInline muted aria-label="카메라 미리보기" />
          <span className="recording">● REC</span>
          <div className="camera-actions"><button className="upload-mode-button" onClick={capture}>찰칵 <span>●</span></button><button className="upload-mode-button" onClick={() => setStream(undefined)}>취소</button></div>
        </> : <>
          <span className="recording">● REC</span>
          <p>사진을 이곳에 끌어다 놓거나 파일을 업로드 해주세요.</p>
          <div className="finder-buttons"><button className="upload-mode-button" onClick={() => fileInput.current?.click()}>SELECT FILE <span>↗</span></button><button className="upload-mode-button" onClick={openCamera}>CAMERA <span>●</span></button></div>
          <small>JPG, PNG, WEBP · MAX 20MB</small>
        </>}
      </div>
    </div>
  </section>;
}
