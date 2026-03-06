# Stage A Frontend Lint Baseline

Generated on 2026-03-06 from `frontend/` with:

```bash
npx eslint .
```

## Scope

- Goal: separate lint issues in touched files from historical debt.
- Result: all current touched frontend files are lint clean.
- Remaining issues below are historical baseline only.

## Summary

- Total remaining historical issues: 66
- Errors: 55
- Warnings: 11
- Touched files with remaining issues: 0

## Touched Files Verified Clean

- `src/App.tsx`
- `src/api/http.ts`
- `src/api/kg.ts`
- `src/components/EditWritebackPanel.tsx`
- `src/components/LeftSearchPanel.tsx`
- `src/components/TopBar.tsx`
- `src/constants/kg.ts`
- `src/hooks/useEntityTypeOptions.ts`
- `src/hooks/useGraphData.ts`
- `src/types/kg.ts`
- `src/utils/httpError.ts`

## Historical Baseline

### `App.tsx`

- 33 errors, 3 warnings
- `@typescript-eslint/no-explicit-any`: lines 40, 41, 72, 97, 103, 141, 225, 262, 276, 305, 361, 392, 405, 423, 446, 461, 465, 469, 483, 486, 503, 520, 557, 574, 625
- `no-empty`: lines 106, 111, 155, 159, 167, 607, 621, 626
- `react-hooks/exhaustive-deps`: lines 433, 566, 610

### `src/components/GraphCanvas.tsx`

- 19 errors, 2 warnings
- `@typescript-eslint/no-explicit-any`: lines 81, 94, 140, 190, 201, 203, 211, 219, 227, 235, 236, 238, 251, 259, 274, 287, 337, 362, 380
- `react-hooks/exhaustive-deps`: lines 325, 357

### `src/components/RelationFilter/RelationFilterPanel.tsx`

- 2 errors
- `react-hooks/set-state-in-effect`: lines 132, 213

### `src/hooks/useEdgeSuggest.ts`

- 2 warnings
- `react-hooks/exhaustive-deps`: lines 194, 206

### `src/hooks/useRawIdSuggest.ts`

- 2 warnings
- `react-hooks/exhaustive-deps`: lines 182, 194

### `src/hooks/useRelationFilter.ts`

- 1 error
- `react-hooks/purity`: line 118

### `src/hooks/useSuggest.ts`

- 2 warnings
- `react-hooks/exhaustive-deps`: lines 188, 200

## Notes

- The root-level `frontend/App.tsx` is still included by `eslint .` and is currently the largest historical source of lint debt.
- This baseline is intended to keep future cleanup incremental and prevent historical issues from being mixed into new change sets.
