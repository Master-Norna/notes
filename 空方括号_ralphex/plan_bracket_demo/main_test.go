package main

import "testing"

var want = map[string]struct {
	beforeGate        string
	afterGate         string
	beforeUncompleted bool
	afterUncompleted  bool
}{
	"slice-type":      {"completed", "continuing", false, true},
	"format-example":  {"completed", "completed", false, false},
	"mixed":           {"continuing", "continuing", true, true},
	"checked-slice":   {"completed", "completed", false, false},
	"bracket-x":       {"completed", "completed", false, false},
	"spaces":          {"completed", "completed", false, false},
	"tab":             {"completed", "continuing", false, true},
	"cli-flag":        {"continuing", "continuing", true, true},
	"array-index":     {"continuing", "continuing", true, true},
	"index-x":         {"completed", "completed", false, false},
	"marker-x":        {"completed", "completed", false, false},
	"no-task-slice":   {"completed", "continuing", false, true},
	"no-task-example": {"completed", "completed", false, false},
}

func TestSyntheticCases(t *testing.T) {
	for _, c := range synthetic {
		w, ok := want[c.name]
		if !ok {
			t.Fatalf("%s: no expectation", c.name)
		}
		p, err := runPair(c.name, c.body)
		if err != nil {
			t.Fatalf("%s: %v", c.name, err)
		}
		if p.before.gate != w.beforeGate || p.before.uncompleted != w.beforeUncompleted {
			t.Errorf("%s before: gate=%s uncompleted=%v, want %s/%v",
				c.name, p.before.gate, p.before.uncompleted, w.beforeGate, w.beforeUncompleted)
		}
		if p.after.gate != w.afterGate || p.after.uncompleted != w.afterUncompleted {
			t.Errorf("%s after: gate=%s uncompleted=%v, want %s/%v",
				c.name, p.after.gate, p.after.uncompleted, w.afterGate, w.afterUncompleted)
		}
	}
}

func TestBracketsInTaskText(t *testing.T) {
	p, err := runPair("slice-type", "# Plan\n\n### Task 1: Convert types\n\n- [ ] convert []string to []T in the callers\n")
	if err != nil {
		t.Fatal(err)
	}
	if len(p.before.boxes) != 1 || len(p.after.boxes) != 1 {
		t.Fatalf("boxes: before=%d after=%d", len(p.before.boxes), len(p.after.boxes))
	}
	if p.before.boxes[0].actionable {
		t.Errorf("parent revision made []string actionable")
	}
	if !p.after.boxes[0].actionable {
		t.Errorf("merged revision still treats []string as a format example")
	}
}

func TestFormatExamplesStillSkipped(t *testing.T) {
	for _, body := range []string{
		"# Plan\n\n### Task 1: Format example\n\n- [ ] use this format for [ ] unchecked items\n",
		"# Plan\n\n### Task 1: Format example\n\n- [ ] use [x] for checked items\n",
		"# Plan\n\n### Task 1: Format example\n\n- [ ] use [  ] for spaced example\n",
	} {
		p, err := runPair("example", body)
		if err != nil {
			t.Fatal(err)
		}
		if len(p.before.boxes) != 1 || len(p.after.boxes) != 1 {
			t.Fatalf("boxes: before=%d after=%d", len(p.before.boxes), len(p.after.boxes))
		}
		if p.before.boxes[0].actionable || p.after.boxes[0].actionable {
			t.Errorf("%q: a format example became actionable (before=%v after=%v)",
				p.before.boxes[0].text, p.before.boxes[0].actionable, p.after.boxes[0].actionable)
		}
	}
}

func TestRealPlanRows(t *testing.T) {
	pairs, err := realPairs()
	if err != nil {
		t.Fatal(err)
	}
	if len(pairs) != 16 {
		t.Fatalf("real rows = %d, want 16", len(pairs))
	}
	for _, p := range pairs {
		if p.before.gate != "completed" {
			t.Errorf("%s: parent gate = %s, want completed", p.name, p.before.gate)
		}
		if p.after.gate != "continuing" {
			t.Errorf("%s: merged gate = %s, want continuing", p.name, p.after.gate)
		}
	}
}
