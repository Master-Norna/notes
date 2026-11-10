package main

import "fmt"

// This demo mirrors the decision order in ralphex pkg/web/session.go and
// session_manager.go around a live dashboard session. The progress file,
// the in-process BroadcastLogger and the file tailer are replaced by slices
// and counters; nothing else is modelled.

type events struct {
	lines []string
}

func (e *events) publish(line string) {
	e.lines = append(e.lines, line)
}

func (e *events) count(line string) int {
	var n int
	for _, got := range e.lines {
		if got == line {
			n++
		}
	}
	return n
}

type session struct {
	file       []string
	lastOffset int
	loaded     bool
	liveOutput bool
	tailing    bool
	events     *events
}

// print is what BroadcastLogger.Print does: write to the progress file and
// publish the same line directly to SSE clients.
func (s *session) print(line string) {
	s.file = append(s.file, line)
	s.events.publish(line)
}

// startTailing is the ordinary file reader. The manager decides whether a
// session gets one; a live-output session must never get one, or the same
// line would be published twice.
func (s *session) startTailing() {
	if s.tailing {
		return
	}
	s.tailing = true
	for _, line := range s.file[s.lastOffset:] {
		s.events.publish(line)
	}
	s.lastOffset = len(s.file)
}

// finishLiveOutput is the merged revision's cleanup: the loaded mark is set
// in the same step that clears the live mark, because the logger already
// streamed the file and the loader must not replay it.
func (s *session) finishLiveOutput() {
	if !s.liveOutput {
		return
	}
	s.liveOutput = false
	s.loaded = true
}

// resetForNewRun hands a reused progress file back to the ordinary tailer.
func (s *session) resetForNewRun() {
	s.loaded = false
	s.liveOutput = false
	s.lastOffset = 0
	s.tailing = false
}

type manager struct {
	merged bool // true: has the liveOutput mark and the !isLiveOutput gates
}

// discoverTailing is SessionManager.updateSession + handleStateTransition for
// an active progress file. The merged revision skips the tailer for a session
// fed by the BroadcastLogger.
func (m *manager) discoverTailing(s *session) {
	if m.merged && s.liveOutput {
		return
	}
	s.startTailing()
}

// discoverCompleted is the loader gate in updateSession: a completed file is
// loaded once, but only when nothing has been ingested yet.
func (m *manager) discoverCompleted(s *session) {
	if m.merged && s.liveOutput {
		return
	}
	if s.loaded {
		return
	}
	s.loaded = true
	if s.lastOffset == 0 {
		for _, line := range s.file {
			s.events.publish(line)
		}
		s.lastOffset = len(s.file)
	}
}

// refresh is SessionManager.RefreshStates for a finished run.
func (m *manager) refresh(s *session) {
	if m.merged {
		s.finishLiveOutput()
	}
	// the parent revision has no live mark; nothing to clear
}

// liveLine runs the watcher discovery of the live progress file while the run
// is still active.
func liveLine(merged bool) int {
	ev := &events{}
	s := &session{events: ev, liveOutput: true}
	m := &manager{merged: merged}

	s.print("unique live line") // BroadcastLogger writes + publishes
	m.discoverTailing(s)        // watcher discovers the same file
	return ev.count("unique live line")
}

// replay runs the directory scan that happens after the live run ended.
func replay(merged bool) int {
	ev := &events{}
	s := &session{events: ev, liveOutput: true}
	m := &manager{merged: merged}

	s.print("unique replay line") // delivered once by the logger
	m.refresh(s)                  // the run ended; RefreshStates runs
	m.discoverCompleted(s)        // a later scan of the same directory
	return ev.count("unique replay line") - 1
}

func main() {
	fmt.Printf("parent: live line delivered %d times, replayed %d after the run\n",
		liveLine(false), replay(false))
	fmt.Printf("merged: live line delivered %d times, replayed %d after the run\n",
		liveLine(true), replay(true))
}
