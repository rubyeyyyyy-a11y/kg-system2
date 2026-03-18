import { useEffect, useRef, useState } from "react";

import type { EditLayoutSection } from "./useEditLayout";

export function useEditDraft(identityKey: string, sections: EditLayoutSection[]) {
  const [draft, setDraft] = useState<Record<string, string>>({});
  const lastIdentityKeyRef = useRef<string>("");

  useEffect(() => {
    const nextValues: Record<string, string> = {};
    sections.forEach((section) => {
      section.fields.forEach((field) => {
        nextValues[field.name] = field.value;
      });
    });
    if (lastIdentityKeyRef.current !== identityKey) {
      lastIdentityKeyRef.current = identityKey;
      setDraft(nextValues);
      return;
    }
    setDraft((prev) => {
      const merged = { ...prev };
      Object.entries(nextValues).forEach(([key, value]) => {
        if (!(key in merged)) merged[key] = value;
      });
      return merged;
    });
  }, [identityKey, sections]);

  return { draft, setDraft };
}
