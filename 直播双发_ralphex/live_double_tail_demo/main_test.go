package main

import "testing"

func TestParentRevision(t *testing.T) {
	if got := liveLine(false); got != 2 {
		t.Fatalf("parent live line deliveries = %d, want 2", got)
	}
	if got := replay(false); got != 1 {
		t.Fatalf("parent replayed lines = %d, want 1", got)
	}
}

func TestMergedRevision(t *testing.T) {
	if got := liveLine(true); got != 1 {
		t.Fatalf("merged live line deliveries = %d, want 1", got)
	}
	if got := replay(true); got != 0 {
		t.Fatalf("merged replayed lines = %d, want 0", got)
	}
}
