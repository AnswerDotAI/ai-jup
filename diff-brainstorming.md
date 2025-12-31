# Sidecar Chat with Notebook Diff Review - Brainstorming

## Overview

This document outlines the design for adding a **sidecar chat panel** to ai-jup that:
1. Sits alongside notebooks in a right sidebar
2. Has the **entire notebook in context** by default
3. Proposes edits/updates to notebook cells
4. Renders **per-cell diffs** the user can accept or reject (Cursor-style UX)

---

## Research Findings

### JupyterLab Sidecar Architecture

From analyzing JupyterLab's extension patterns and the jupyter-chat library:

- **Shell areas**: Use `app.shell.add(widget, 'right', { rank: 900 })` for sidecar panels
- **Notebook tracking**: `INotebookTracker` provides access to active notebook and cells
- **Cell access**: `notebookPanel.model.cells` for read/write, `cell.sharedModel.setSource()` for edits
- **Widget pattern**: Extend `ReactWidget` for React-based UI components
- **Signal reactivity**: Use Lumino `Signal` for model→view updates (same pattern as jupyter-chat)

### Cursor's Diff Interface

Based on Cursor's documentation and feature pages:

| Feature | Description |
|---------|-------------|
| **Color-coded lines** | Green for additions, red for deletions, neutral for context |
| **File-by-file review** | Floating review bar at bottom with Accept/Reject per file |
| **Selective acceptance** | Can accept/reject individual lines within a file |
| **Review workflow** | "Accept all" or "Reject all" + navigate between changes |

For notebooks, we adapt this to **per-cell** granularity instead of per-file.

### nbdime (Notebook Diff/Merge)

The official Jupyter tool for notebook diffing:
- `diff_notebooks(base, remote)` produces structured diff operations
- Understands cell types, metadata, outputs
- Has JupyterLab extension integration
- Operations: `add`, `remove`, `replace`, `patch` (recursive)

For v1, we can use a simpler approach (direct source comparison) and upgrade to nbdime later.

---

## Architecture

### High-Level Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                      JupyterLab Application                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Main Area (Notebook)              │  Right Sidebar          │  │
│  │  ┌────────────────────────────┐    │  ┌────────────────────┐ │  │
│  │  │ Cell 0 [code]              │    │  │ ChatSidecarWidget  │ │  │
│  │  │ Cell 1 [markdown]          │    │  │ ┌────────────────┐ │ │  │
│  │  │ Cell 2 [code]              │    │  │ │ ChatHeader     │ │ │  │
│  │  │ ...                        │    │  │ │ (notebook name)│ │ │  │
│  │  └────────────────────────────┘    │  │ ├────────────────┤ │ │  │
│  │                                    │  │ │ MessageList    │ │ │  │
│  │                                    │  │ │ (chat bubbles) │ │ │  │
│  │                                    │  │ ├────────────────┤ │ │  │
│  │                                    │  │ │ DiffReviewPanel│ │ │  │
│  │                                    │  │ │ (per-cell diffs│ │ │  │
│  │                                    │  │ │  accept/reject)│ │ │  │
│  │                                    │  │ ├────────────────┤ │ │  │
│  │                                    │  │ │ ChatInput      │ │ │  │
│  │                                    │  │ └────────────────┘ │ │  │
│  │                                    │  └────────────────────┘ │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### New Files/Modules

```
src/
├── chat/
│   ├── ChatSidecarWidget.tsx      # Main ReactWidget for sidecar
│   ├── ChatModel.ts               # Chat state: messages, edits, streaming
│   ├── NotebookChatManager.ts     # Controller for per-notebook chat sessions
│   ├── components/
│   │   ├── ChatHeader.tsx         # Title bar with notebook name
│   │   ├── MessageList.tsx        # Chat message bubbles
│   │   ├── ChatInput.tsx          # Text input + send button
│   │   ├── DiffReviewPanel.tsx    # Container for all cell diffs
│   │   ├── CellDiffView.tsx       # Single cell diff with accept/reject
│   │   └── DiffSummaryBar.tsx     # "3 cells modified" + bulk actions
│   ├── diffUtils.ts               # Line-level diff computation
│   └── notebookSerializer.ts      # Serialize notebook for LLM context
├── chatSidecarPlugin.ts           # JupyterLab plugin registration
└── index.ts                       # (add new plugin to exports)
```

---

## Implementation Plan

### 1. Notebook Serialization for LLM Context

**Goal**: Give LLM the entire notebook in a format it can understand and reference.

```typescript
interface SerializedCell {
  index: number;
  id: string;              // Stable cell ID (survives reordering)
  cell_type: 'code' | 'markdown' | 'raw';
  source: string;
  execution_count?: number;
}

interface SerializedNotebook {
  path: string;
  cells: SerializedCell[];
}

function serializeNotebook(panel: NotebookPanel): SerializedNotebook {
  const nbModel = panel.context.model;
  const nbJson = nbModel.toJSON();
  return {
    path: panel.context.path,
    cells: nbJson.cells.map((cell, index) => ({
      index,
      id: cell.id || String(index),
      cell_type: cell.cell_type,
      source: Array.isArray(cell.source) ? cell.source.join('') : cell.source,
      execution_count: cell.execution_count ?? undefined
    }))
  };
}

// Text format for LLM prompt
function notebookToPromptText(nb: SerializedNotebook): string {
  return nb.cells.map(c => 
    `# Cell ${c.index} [id=${c.id}] (${c.cell_type})\n${c.source}\n`
  ).join('\n');
}
```

### 2. Edit Plan Format (LLM → Frontend)

The LLM outputs edits in a structured JSON format:

```typescript
type CellEditKind = 'modify' | 'insert_before' | 'insert_after' | 'delete';

interface ModifyCellEdit {
  kind: 'modify';
  target_cell_id: string;
  new_source: string;
  new_cell_type?: 'code' | 'markdown';
}

interface InsertCellEdit {
  kind: 'insert_before' | 'insert_after';
  target_cell_id: string;       // Reference cell
  new_cell_type: 'code' | 'markdown';
  new_source: string;
}

interface DeleteCellEdit {
  kind: 'delete';
  target_cell_id: string;
}

type CellEdit = ModifyCellEdit | InsertCellEdit | DeleteCellEdit;

interface NotebookEditPlan {
  reason?: string;              // Explanation for the user
  edits: CellEdit[];
}
```

**LLM output format** (in assistant message):

```
Here's what I'll change:

<<<AI_JUP_PATCH_START>>>
{
  "reason": "Added error handling and fixed the loop",
  "edits": [
    {
      "kind": "modify",
      "target_cell_id": "abc123",
      "new_source": "def process_data(df):\n    try:\n        ...\n    except Exception as e:\n        print(f'Error: {e}')"
    },
    {
      "kind": "insert_after",
      "target_cell_id": "abc123",
      "new_cell_type": "markdown",
      "new_source": "## Data Processing Results"
    }
  ]
}
<<<AI_JUP_PATCH_END>>>
```

### 3. Diff Model for UI

After parsing the edit plan, build diff models for the UI:

```typescript
interface CellDiffModel {
  id: string;                   // Unique diff ID
  targetCellId: string;         // Which cell this affects
  diffType: 'modify' | 'insert' | 'delete';
  original?: SerializedCell;    // undefined for insert
  proposed?: SerializedCell;    // undefined for delete
  lineDiff?: LineDiff[];        // For modify: per-line changes
  status: 'pending' | 'accepted' | 'rejected';
}

interface LineDiff {
  type: 'add' | 'remove' | 'unchanged';
  content: string;
  lineNumber: number;
}

interface DiffSessionModel {
  notebookSnapshot: SerializedNotebook;  // State when edit was generated
  editPlan: NotebookEditPlan;
  cellDiffs: CellDiffModel[];
  pendingCount: number;
  acceptedCount: number;
  rejectedCount: number;
}
```

### 4. UI Components

#### CellDiffView (Cursor-like per-cell diff)

```
┌─────────────────────────────────────────────────────────┐
│ Cell 2 [code] - Modified                    [✓] [✗]    │
├─────────────────────────────────────────────────────────┤
│   1  │ def process_data(df):                            │
│ - 2  │     for item in df:                   (red bg)   │
│ + 2  │     for idx, item in enumerate(df):   (green bg) │
│   3  │         result = transform(item)                 │
│ + 4  │         print(f"Processing {idx}")    (green bg) │
│   5  │     return result                                │
└─────────────────────────────────────────────────────────┘
```

Key features:
- **Line numbers** with gutter
- **Color coding**: green for additions, red for deletions
- **Accept/Reject buttons** per cell
- **Collapse after action** (or show badge)

#### DiffSummaryBar (floating at bottom)

```
┌─────────────────────────────────────────────────────────┐
│ 3 changes remaining  │ [Accept All] [Reject All] [↑][↓]│
└─────────────────────────────────────────────────────────┘
```

### 5. Applying Changes to Notebook

When user clicks "Accept" on a cell diff:

```typescript
function applyCellEdit(
  panel: NotebookPanel,
  edit: CellEdit,
  cellIdMap: Map<string, number>  // id → current index
): void {
  const notebook = panel.content;
  const model = notebook.model;
  
  const targetIndex = cellIdMap.get(edit.target_cell_id);
  if (targetIndex === undefined) {
    console.warn(`Cell ${edit.target_cell_id} not found`);
    return;
  }

  switch (edit.kind) {
    case 'modify': {
      const cell = model.cells.get(targetIndex);
      cell.sharedModel.setSource(edit.new_source);
      if (edit.new_cell_type && cell.type !== edit.new_cell_type) {
        // Type change requires cell replacement
        NotebookActions.changeCellType(notebook, edit.new_cell_type);
      }
      break;
    }
    case 'insert_before':
    case 'insert_after': {
      const insertIndex = edit.kind === 'insert_before' 
        ? targetIndex 
        : targetIndex + 1;
      const newCell = model.contentFactory.createCell(
        edit.new_cell_type,
        { source: edit.new_source }
      );
      model.cells.insert(insertIndex, newCell);
      break;
    }
    case 'delete': {
      model.cells.remove(targetIndex);
      break;
    }
  }
}
```

### 6. Backend Changes

Extend `handlers.py` to support chat mode:

```python
# In _build_system_prompt()
mode = context.get("mode", "prompt-cell")

if mode == "chat-notebook-edit":
    system_prompt += """
## Notebook Context
The user's notebook is provided below. Each cell is labeled with its index and ID.

When proposing changes, output a JSON patch between these markers:
<<<AI_JUP_PATCH_START>>>
{
  "reason": "Brief explanation",
  "edits": [
    {"kind": "modify", "target_cell_id": "...", "new_source": "..."},
    {"kind": "insert_after", "target_cell_id": "...", "new_cell_type": "code", "new_source": "..."},
    {"kind": "delete", "target_cell_id": "..."}
  ]
}
<<<AI_JUP_PATCH_END>>>

Only include a patch when the user explicitly asks for code changes.
For questions/explanations, respond normally without a patch.
"""
```

---

## Technical Challenges & Solutions

### Challenge 1: LLM JSON Reliability

**Problem**: Model might output malformed JSON or skip markers.

**Solutions**:
- Strict system prompt with examples
- Only parse between markers (ignore other text)
- If parse fails, show error banner + raw text
- Future: Add validation/retry logic

### Challenge 2: Cell ID Stability

**Problem**: User may edit/reorder cells between snapshot and applying patch.

**Solutions**:
- Use `cell.id` (stable) over `index` (can change)
- When applying: resolve ID to current index
- If cell not found, mark edit as "outdated" with warning
- Consider: timestamp-based staleness detection

### Challenge 3: Large Notebooks

**Problem**: Entire notebook in context can exceed token limits.

**Solutions**:
- Truncate cell sources to N chars (e.g., 4000)
- Optional "summarize" mode for very long cells
- UI toggle: "Include all cells" vs "Recent cells only"
- Track token usage and warn user

### Challenge 4: Line-Level Diffing

**Problem**: Need to show per-line changes within cells.

**Solutions**:
- Use `diff` npm package for line-level comparison
- Simple algorithm: split by newline, compute LCS-based diff
- Later: upgrade to nbdime for richer diffs (outputs, metadata)

### Challenge 5: Streaming + Patch Extraction

**Problem**: LLM streams text; need to extract JSON after completion.

**Solution**:
```typescript
// In ChatModel after stream completes
onStreamComplete(fullText: string) {
  const match = fullText.match(
    /<<<AI_JUP_PATCH_START>>>([\s\S]*?)<<<AI_JUP_PATCH_END>>>/
  );
  if (match) {
    try {
      const plan: NotebookEditPlan = JSON.parse(match[1].trim());
      this.attachEditPlan(plan);
    } catch (e) {
      this.setEditPlanError('Invalid JSON in patch');
    }
  }
}
```

---

## Implementation Phases

### Phase 1: Basic Sidecar (MVP)
- [ ] Create ChatSidecarWidget with basic chat UI
- [ ] Serialize notebook and send to existing `/ai-jup/prompt` endpoint
- [ ] Display streaming responses
- [ ] No diff UI yet (text-only responses)

### Phase 2: Edit Plan Parsing
- [ ] Update system prompt for chat-notebook-edit mode
- [ ] Parse `NotebookEditPlan` from assistant messages
- [ ] Build `DiffSessionModel` from edit plan

### Phase 3: Diff Review UI
- [ ] Implement `CellDiffView` component with line-level diffs
- [ ] Add accept/reject buttons per cell
- [ ] Implement `DiffSummaryBar` with bulk actions
- [ ] Apply accepted changes to notebook

### Phase 4: Polish
- [ ] Keyboard shortcuts (Enter to accept, Escape to reject)
- [ ] Navigate between changes with arrow keys
- [ ] Visual indicators in notebook (highlight modified cells)
- [ ] Persistence: save chat history per notebook
- [ ] Settings: model selection, token limits, UI preferences

---

## Comparison with Existing Features

| Feature | Prompt Cells | Sidecar Chat |
|---------|-------------|--------------|
| **Context** | Preceding cells + `$var` + `&func` | Entire notebook |
| **Output** | Inline in notebook | Sidebar panel |
| **Edits** | Generates new cells below | Proposes diffs to existing cells |
| **Interaction** | Single-shot | Conversational |
| **Best for** | Local, focused tasks | Refactoring, cross-cell changes |

---

## Undo/Revert UX Design

### Core Principle

**Use JupyterLab's existing undo stack as the single source of truth**, then layer a thin "AI changes" metadata tracker on top for better UX.

### Approach: Stack-Based Undo + AI Metadata

```
┌─────────────────────────────────────────────────────────────────┐
│                    JupyterLab Undo Stack                        │
│  (single source of truth for all cell edits)                    │
├─────────────────────────────────────────────────────────────────┤
│  ... → Manual Edit → AI Change → Manual Edit → AI Change → ... │
└─────────────────────────────────────────────────────────────────┘
                              ↑
┌─────────────────────────────────────────────────────────────────┐
│                    AI Changes Metadata                          │
│  (lightweight tracking layer - does NOT duplicate history)      │
├─────────────────────────────────────────────────────────────────┤
│  {                                                              │
│    sessionId: "resp-123",                                       │
│    changeId: "chg-456",                                         │
│    cellId: "abc123",                                            │
│    type: "modify",                                              │
│    undoDepthAfter: 7,      // stack depth after applying        │
│    hasSubsequentEdits: false                                    │
│  }                                                              │
└─────────────────────────────────────────────────────────────────┘
```

### Undo Mechanisms

#### 1. Immediate Undo (Cmd+Z)

Works exactly as expected:
- User accepts AI change → presses Cmd+Z → change reverts
- Show ephemeral hint after accept: *"Change applied — press Cmd+Z to undo"*

#### 2. Inline "Undo" Button (Per-Cell)

After accepting a cell change, the UI updates:

```
Before accept:
┌──────────────────────────────────────┐
│ Cell 2 [code] - Modified   [✓] [✗]  │  ← Accept / Reject
└──────────────────────────────────────┘

After accept:
┌──────────────────────────────────────┐
│ Cell 2 [code] - Accepted ✓  [Undo]  │  ← Undo button appears
└──────────────────────────────────────┘
```

**Undo button behavior:**
- If this was the last change → calls `undo()` once
- If there were subsequent edits → shows warning, then calls `undo()` N times

#### 3. "Undo Back to Here" (Later Undo)

For changes that aren't at the top of the stack:

```
┌──────────────────────────────────────────────────────────────┐
│ Cell 2 - Accepted (edited) ⚠        [Undo back to here]     │
│ ↳ "This cell has been edited since. Undo will also          │
│    revert those later edits."                                │
└──────────────────────────────────────────────────────────────┘
```

**Implementation:**
```typescript
function undoBackToChange(changeMetadata: AIChangeMetadata) {
  const stepsToUndo = currentStackDepth - changeMetadata.undoDepthAfter;
  for (let i = 0; i < stepsToUndo; i++) {
    notebookModel.undo();
  }
}
```

#### 4. Session-Level Undo

In the chat sidebar, per AI response:

```
┌──────────────────────────────────────────────────────────────┐
│ 🤖 AI Response                                               │
│ "I've updated the data processing function..."               │
│                                                              │
│ Applied to 3 cells                    [Undo entire response] │
└──────────────────────────────────────────────────────────────┘
```

**Implementation:**
- If "Accept All" was used → one compound transaction → one `undo()` call
- If individual accepts → track all `undoDepthAfter` values, undo back to earliest

### Handling Edge Cases

#### Cell Modifications
| Scenario | Behavior |
|----------|----------|
| Immediate undo | Cmd+Z reverts to pre-AI state |
| Later undo | "Undo back to here" reverts all changes after |
| With manual edits after | Warning shown, reverts manual edits too |

#### Cell Insertions
| Scenario | Behavior |
|----------|----------|
| Undo insert | Cell disappears (JupyterLab handles index restoration) |
| Later undo | Any edits made to inserted cell are also lost |

#### Cell Deletions (Critical!)
| Scenario | Behavior |
|----------|----------|
| Undo delete | Cell restored with full content at original position |
| Implementation | JupyterLab's undo stack already stores deleted cell data |
| No extra work needed | Just call `undo()` - restoration is automatic |

#### Manual Edits After AI Change
```
Timeline: Accept AI → Type manually → Press Cmd+Z
Result:   First undo = manual edit
          Second undo = AI change
```
This is standard JupyterLab behavior - document it clearly.

### Visual Indicators

#### In the Sidecar Panel

| State | Badge | Controls | Tooltip |
|-------|-------|----------|---------|
| Pending | "Suggestion" | [Accept] [Reject] | - |
| Accepted (clean) | "Accepted ✓" | [Undo] | "Undo this change (Cmd+Z)" |
| Accepted (edited) | "Accepted ⚠" | [Undo back to here] | "Will undo later edits too" |
| Reverted | "Reverted" (grey) | - | - |

#### In the Notebook (Optional)

Add subtle gutter markers on cells with AI history:

```
┌─────┬────────────────────────────────────────┐
│ 🟢 │ def process_data(df):                  │  ← Green: AI change, no edits after
│    │     ...                                │
├─────┼────────────────────────────────────────┤
│ 🟡 │ def validate(x):                       │  ← Yellow: AI change + manual edits
│    │     ...                                │
├─────┼────────────────────────────────────────┤
│    │ # Normal cell                          │  ← No marker: no AI involvement
└─────┴────────────────────────────────────────┘
```

Hover on marker → tooltip: *"AI suggestion applied · Click to view in chat"*

### Metadata Schema

```typescript
interface AIChangeMetadata {
  sessionId: string;           // Which AI response this came from
  changeId: string;            // Unique ID for this specific change
  cellId: string;              // Target cell's stable ID
  type: 'modify' | 'insert' | 'delete';
  timestamp: number;
  undoDepthAfter: number;      // Undo stack depth after applying
  cellVersionAtAccept: number; // To detect subsequent edits
}

interface AISessionMetadata {
  sessionId: string;
  messageId: string;           // Link to chat message
  changes: AIChangeMetadata[];
  appliedAt: number;
}
```

### Tracking Subsequent Edits

```typescript
// On any cell change (source, outputs, metadata)
function onCellChanged(cell: ICellModel) {
  const aiChange = findAIChangeForCell(cell.id);
  if (aiChange && cell.version > aiChange.cellVersionAtAccept) {
    aiChange.hasSubsequentEdits = true;
    // Update UI to show ⚠ indicator
  }
}
```

### Why This Approach?

| Alternative | Why Not |
|-------------|---------|
| **Full snapshots** | Memory heavy, conflicts with JupyterLab's granular undo |
| **Git-style checkpoints** | Overkill, requires merge logic, more mental model |
| **Custom undo stack** | Duplicates work, inconsistent with Cmd+Z behavior |

**Benefits of stack-based + metadata:**
- Cmd+Z works everywhere (consistent UX)
- Deleted cells restored automatically (JupyterLab handles it)
- Lightweight metadata (no content duplication)
- Clear mental model: time-travel undo

### Implementation Guardrails

1. **Group AI edits into transactions**
   ```typescript
   // Apply cell change as single undo unit
   model.transact(() => {
     cell.sharedModel.setSource(newSource);
   });
   // Record metadata immediately after
   recordAIChange({ undoDepthAfter: undoManager.stackLength, ... });
   ```

2. **Validate before undo**
   ```typescript
   function canUndoAIChange(change: AIChangeMetadata): boolean {
     // If stack is shorter than expected, change is no longer undoable
     return currentStackDepth >= change.undoDepthAfter;
   }
   ```

3. **Clear warnings for destructive actions**
   - Always warn when undoing will affect later manual edits
   - Consider confirmation dialog for "Undo entire response" with many changes

---

## Decisions

1. **Multi-notebook context**: Not needed for v1 (single notebook only)
2. **Collaborative editing**: Not supported for v1 (single user)

## Open Questions

1. ~~**Undo support**: Should accepting changes be undoable?~~ ✅ Designed above
2. **Conflict resolution**: What if user edits a cell while a patch is pending?
3. **Output cells**: Should AI be able to propose clearing/modifying outputs?
4. **Metadata**: Should we expose cell metadata to the AI?

---

## References

- [jupyter-chat](https://github.com/jupyterlab/jupyter-chat) - Official JupyterLab chat patterns
- [jupyter-ai](https://github.com/jupyterlab/jupyter-ai) - AI integration patterns
- [nbdime](https://github.com/jupyter/nbdime) - Notebook diff/merge tools
- [Cursor Review Docs](https://cursor.com/docs/agent/review) - Diff review UX patterns
- [jupyterlab-sidecar](https://github.com/jupyter-widgets/jupyterlab-sidecar) - Sidecar widget patterns
