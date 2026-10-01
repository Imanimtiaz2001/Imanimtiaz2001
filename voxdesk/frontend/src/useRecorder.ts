import { useCallback, useEffect, useRef, useState } from 'react';

export function useRecorder(
  onComplete: (file: File) => void,
  onError: (message: string) => void,
  maxSeconds = 60,
) {
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [starting, setStarting] = useState(false);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const cancelled = useRef(false);
  const mounted = useRef(true);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const completeRef = useRef(onComplete);
  completeRef.current = onComplete;
  const errorRef = useRef(onError);
  errorRef.current = onError;
  const cleanup = useCallback(() => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
    if (mounted.current) {
      setRecording(false);
      setStarting(false);
    }
  }, []);
  const stop = useCallback(
    (discard = false) => {
      cancelled.current = discard;
      if (recorder.current?.state === 'recording') recorder.current.stop();
      cleanup();
    },
    [cleanup],
  );
  const start = useCallback(async () => {
    if (starting || recording) return;
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      errorRef.current(
        'Microphone recording requires a supported browser on HTTPS or localhost. You can still upload audio.',
      );
      return;
    }
    cancelled.current = false;
    setStarting(true);
    try {
      const media = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      if (cancelled.current || !mounted.current) {
        media.getTracks().forEach((track) => track.stop());
        return;
      }
      stream.current = media;
      const mime = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/webm'].find((item) =>
        MediaRecorder.isTypeSupported(item),
      );
      const instance = new MediaRecorder(media, mime ? { mimeType: mime } : undefined);
      recorder.current = instance;
      const chunks: BlobPart[] = [];
      instance.ondataavailable = (event) => {
        if (event.data.size) chunks.push(event.data);
      };
      instance.onerror = () => {
        cancelled.current = true;
        cleanup();
        errorRef.current('Recording failed. Please try again or upload an audio file.');
      };
      instance.onstop = () => {
        cleanup();
        if (!cancelled.current && mounted.current) {
          const blob = new Blob(chunks, { type: instance.mimeType || 'audio/webm' });
          if (!blob.size) {
            errorRef.current('The recording was empty. Please try again.');
            return;
          }
          completeRef.current(
            new File(
              [blob],
              instance.mimeType.includes('mp4') ? 'recording.m4a' : 'recording.webm',
              { type: blob.type },
            ),
          );
        }
      };
      instance.start(250);
      setSeconds(0);
      setStarting(false);
      setRecording(true);
      let elapsed = 0;
      timer.current = setInterval(() => {
        elapsed++;
        setSeconds(elapsed);
        if (elapsed >= maxSeconds) stop();
      }, 1000);
    } catch (error) {
      cleanup();
      if (!cancelled.current)
        errorRef.current(
          error instanceof DOMException && error.name === 'NotAllowedError'
            ? 'Microphone access was denied. Allow it in browser settings or upload an audio file.'
            : 'Could not open the microphone. Check that it is connected and try again.',
        );
    }
  }, [cleanup, maxSeconds, recording, starting, stop]);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      cancelled.current = true;
      if (recorder.current?.state === 'recording') recorder.current.stop();
      cleanup();
    };
  }, [cleanup]);
  return { recording, starting, seconds, start, stop };
}
