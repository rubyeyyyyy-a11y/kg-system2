import type { EditLayoutSection } from "../hooks/useEditLayout";
import { EditField } from "./EditField";
import { EditSection } from "./EditSection";

export function DynamicEditForm({
  sections,
  draft,
  disabled,
  onChange,
}: {
  sections: EditLayoutSection[];
  draft: Record<string, string>;
  disabled?: boolean;
  onChange: (fieldName: string, next: string) => void;
}) {
  return (
    <div style={{ display: "grid", gap: 10 }}>
      {sections.map((section) => (
        <EditSection key={section.key} title={section.title}>
          {section.fields.map((field) => (
            <EditField
              key={field.name}
              field={field}
              value={draft[field.name] || ""}
              disabled={disabled}
              onChange={(next) => onChange(field.name, next)}
            />
          ))}
        </EditSection>
      ))}
    </div>
  );
}
