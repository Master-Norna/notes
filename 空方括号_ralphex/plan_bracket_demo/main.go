// Command plan-bracket-demo feeds the same plan text to the two revisions of
// ralphex pkg/plan/parse.go. The only difference between them is one character
// in formatInText: `\[\s*[ xX]?\s*\]` before, `\[\s*[ xX]\s*\]` after.
//
// The completion gate mirrors TaskPhase.HasUncompletedTasks in
// pkg/processor/phase/task.go: walk the parsed tasks first; only when the plan
// parsed zero tasks fall back to FileHasUncompletedCheckbox.
package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	after "plan-bracket-demo/after"
	before "plan-bracket-demo/before"
)

type boxView struct {
	text       string
	checked    bool
	actionable bool
}

type caseView struct {
	boxes       []boxView
	uncompleted bool
	gate        string
}

type pair struct {
	name   string
	before caseView
	after  caseView
}

var synthetic = []struct {
	name string
	body string
}{
	{"slice-type", "# Plan\n\n### Task 1: Convert types\n\n- [ ] convert []string to []T in the callers\n"},
	{"format-example", "# Plan\n\n### Task 1: Format example\n\n- [x] Faulti format\n- [ ] use this format for [ ] unchecked items\n"},
	{"mixed", "# Plan\n\n### Task 1: Mixed\n\n- [ ] Create HashPassword\n- [ ] use [ ] for format example\n"},
	{"checked-slice", "# Plan\n\n### Task 1: Done\n\n- [x] Add `ClaudeErrorPatterns []string` to `Values` struct\n"},
	{"bracket-x", "# Plan\n\n### Task 1: Format example\n\n- [ ] use [x] for checked items\n"},
	{"spaces", "# Plan\n\n### Task 1: Spaced example\n\n- [ ] use [  ] for spaced example\n"},
	{"tab", "# Plan\n\n### Task 1: Tab example\n\n- [ ] use [\t] for tab example\n"},
	{"cli-flag", "# Plan\n\n### Task 1: Flag\n\n- [ ] add a `--dry-run[=true]` flag\n"},
	{"array-index", "# Plan\n\n### Task 1: Array\n\n- [ ] read a[0] before the loop\n"},
	{"index-x", "# Plan\n\n### Task 1: Index\n\n- [ ] fix the s[x] indexing bug\n"},
	{"marker-x", "# Plan\n\n### Task 1: Marker\n\n- [ ] mark all tasks [x] when done\n"},
	{"no-task-slice", "# Plan\n\n- [ ] convert []string to []T in the callers\n"},
	{"no-task-example", "# Plan\n\n- [ ] use this format for [ ] unchecked items\n"},
}

func evalBefore(content, path string) (caseView, error) {
	p, err := before.ParsePlan(content)
	if err != nil {
		return caseView{}, err
	}
	var v caseView
	for _, t := range p.Tasks {
		for _, cb := range t.Checkboxes {
			v.boxes = append(v.boxes, boxView{cb.Text, cb.Checked, cb.IsActionable()})
		}
	}
	for _, t := range p.Tasks {
		if t.HasUncompletedActionableWork() {
			v.uncompleted = true
		}
	}
	if len(p.Tasks) == 0 {
		has, err := before.FileHasUncompletedCheckbox(path)
		if err != nil {
			return v, err
		}
		v.uncompleted = has
	}
	if v.uncompleted {
		v.gate = "continuing"
	} else {
		v.gate = "completed"
	}
	return v, nil
}

func evalAfter(content, path string) (caseView, error) {
	p, err := after.ParsePlan(content)
	if err != nil {
		return caseView{}, err
	}
	var v caseView
	for _, t := range p.Tasks {
		for _, cb := range t.Checkboxes {
			v.boxes = append(v.boxes, boxView{cb.Text, cb.Checked, cb.IsActionable()})
		}
	}
	for _, t := range p.Tasks {
		if t.HasUncompletedActionableWork() {
			v.uncompleted = true
		}
	}
	if len(p.Tasks) == 0 {
		has, err := after.FileHasUncompletedCheckbox(path)
		if err != nil {
			return v, err
		}
		v.uncompleted = has
	}
	if v.uncompleted {
		v.gate = "continuing"
	} else {
		v.gate = "completed"
	}
	return v, nil
}

func runPair(name, content string) (pair, error) {
	dir, err := os.MkdirTemp("", "plan-bracket-")
	if err != nil {
		return pair{}, err
	}
	defer os.RemoveAll(dir)
	path := filepath.Join(dir, "plan.md")
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		return pair{}, err
	}
	b, err := evalBefore(content, path)
	if err != nil {
		return pair{}, err
	}
	a, err := evalAfter(content, path)
	if err != nil {
		return pair{}, err
	}
	return pair{name: name, before: b, after: a}, nil
}

func label(v caseView) string {
	if len(v.boxes) == 0 {
		return "no task section, " + v.gate
	}
	for _, b := range v.boxes {
		if !b.checked && b.actionable {
			return "actionable, " + v.gate
		}
	}
	return "not actionable, " + v.gate
}

type realRow struct {
	source string
	text   string
}

func loadRealRows(path string) ([]realRow, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var rows []realRow
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSuffix(line, "\r")
		if strings.TrimSpace(line) == "" {
			continue
		}
		parts := strings.SplitN(line, "\t", 2)
		if len(parts) != 2 {
			return nil, fmt.Errorf("bad fixture line: %q", line)
		}
		rows = append(rows, realRow{source: parts[0], text: parts[1]})
	}
	return rows, nil
}

func realPairs() ([]pair, error) {
	rows, err := loadRealRows(filepath.Join("fixtures", "real_checkboxes.tsv"))
	if err != nil {
		return nil, err
	}
	out := make([]pair, 0, len(rows))
	for _, r := range rows {
		p, err := runPair(r.source, "# Plan\n\n### Task 1: Real task\n\n- [ ] "+r.text+"\n")
		if err != nil {
			return nil, err
		}
		out = append(out, p)
	}
	return out, nil
}

func countNotActionable(pairs []pair) (int, int) {
	var b, a int
	for _, p := range pairs {
		if p.before.gate == "completed" {
			b++
		}
		if p.after.gate == "completed" {
			a++
		}
	}
	return b, a
}

func main() {
	fmt.Printf("%-18s %-28s %s\n", "case", "before", "after")
	for _, c := range synthetic {
		p, err := runPair(c.name, c.body)
		if err != nil {
			fmt.Fprintf(os.Stderr, "%s: %v\n", c.name, err)
			os.Exit(1)
		}
		fmt.Printf("%-18s %-28s %s\n", p.name, label(p.before), label(p.after))
	}
	pairs, err := realPairs()
	if err != nil {
		fmt.Fprintf(os.Stderr, "real plans: %v\n", err)
		os.Exit(1)
	}
	b, a := countNotActionable(pairs)
	fmt.Printf("\nreal docs/plans rows: %d\n", len(pairs))
	fmt.Printf("  before: %d/%d rows end the gate as completed\n", b, len(pairs))
	fmt.Printf("  after:  %d/%d rows end the gate as completed\n", a, len(pairs))
}
