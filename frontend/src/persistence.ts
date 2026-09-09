import { useEffect, useState } from "react";
export function readStored<T>(key: string, fallback: T): T {
  try {
    const text = localStorage.getItem("practice-" + key);
    return text ? (JSON.parse(text) as T) : fallback;
  } catch {
    return fallback;
  }
}
export function storeDraft(key: string, value: unknown): boolean {
  try {
    localStorage.setItem("practice-" + key, JSON.stringify(value));
    return true;
  } catch {
    window.dispatchEvent(new Event("practice-storage-error"));
    return false;
  }
}
export function useDraft<T>(key: string, fallback: T): [T, (value: T) => void] {
  const [value, setValue] = useState(() => readStored(key, fallback));
  useEffect(() => {
    setValue(readStored(key, fallback));
  }, [key]);
  return [
    value,
    (next: T) => {
      setValue(next);
      storeDraft(key, next);
    },
  ];
}
export function exportText(text: string, filename = "practice-draft.py") {
  const url = URL.createObjectURL(
    new Blob([text], { type: "text/plain;charset=utf-8" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
