import { useCallback, useRef } from "react";

type LiveVideoRefMap = Map<string, HTMLVideoElement>;

type LivePhotoHoverHandlers = {
  registerVideoRef: (assetId: string) => (element: HTMLVideoElement | null) => void;
  handleMouseEnter: (assetId: string) => void;
  handleMouseLeave: (assetId: string) => void;
};

export function useLivePhotoHover(): LivePhotoHoverHandlers {
  const videoRefs = useRef<LiveVideoRefMap>(new Map());

  const registerVideoRef = useCallback(
    (assetId: string) => (element: HTMLVideoElement | null) => {
      if (element) {
        videoRefs.current.set(assetId, element);
      } else {
        videoRefs.current.delete(assetId);
      }
    },
    []
  );

  const handleMouseEnter = useCallback((assetId: string) => {
    const video = videoRefs.current.get(assetId);
    if (!video || video.dataset.failed === "true") {
      return;
    }
    try {
      video.currentTime = 0;
    } catch {
      // Ignore seek errors for unbuffered videos.
    }
    const playPromise = video.play();
    if (playPromise && typeof playPromise.catch === "function") {
      playPromise.catch(() => {
        // Ignore autoplay interruptions.
      });
    }
  }, []);

  const handleMouseLeave = useCallback((assetId: string) => {
    const video = videoRefs.current.get(assetId);
    if (!video) {
      return;
    }
    video.pause();
    try {
      video.currentTime = 0;
    } catch {
      // Ignore seek errors for unbuffered videos.
    }
  }, []);

  return { registerVideoRef, handleMouseEnter, handleMouseLeave };
}
