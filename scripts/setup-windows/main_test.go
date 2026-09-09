package main

import (
	"archive/zip"
	"os"
	"path/filepath"
	"testing"
)

// writeZip builds a test zip whose entries are given as "path/inside/zip"
// (files only; directories are implied and get one byte of content).
func writeZip(t *testing.T, path string, entries []string) {
	t.Helper()
	f, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	w := zip.NewWriter(f)
	for _, name := range entries {
		fw, err := w.Create(name)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := fw.Write([]byte("x")); err != nil {
			t.Fatal(err)
		}
	}
	if err := w.Close(); err != nil {
		t.Fatal(err)
	}
}

func assertFile(t *testing.T, path string) {
	t.Helper()
	if _, err := os.Stat(path); err != nil {
		t.Errorf("expected file %s to exist: %v", path, err)
	}
}

// The README warns the zip may or may not wrap its contents in an extra
// top-level folder. Both layouts must land the same way in data/Ashen_Era_Archive.
func TestUnzipAndPlace_FlatLayout(t *testing.T) {
	dir := t.TempDir()
	zipPath := filepath.Join(dir, "archive.zip")
	writeZip(t, zipPath, []string{
		"wiki/page1.md",
		"codex/vol1.pdf",
		"chronicles/vol1.docx",
		"ephemera/letter1.md",
		"images/plate.png",
		"README.txt",
	})

	extractDir := filepath.Join(dir, "extract")
	if err := unzip(zipPath, extractDir); err != nil {
		t.Fatal(err)
	}
	src, err := findWikiParent(extractDir)
	if err != nil {
		t.Fatal(err)
	}
	if src != extractDir {
		t.Errorf("flat layout: expected src == extractDir, got %s", src)
	}

	dataDir := filepath.Join(dir, "data", "Ashen_Era_Archive")
	if err := moveDirContents(src, dataDir); err != nil {
		t.Fatal(err)
	}
	if !archivePresent(dataDir) {
		t.Fatal("expected all 5 subdirs present after placement")
	}
	assertFile(t, filepath.Join(dataDir, "wiki", "page1.md"))
	assertFile(t, filepath.Join(dataDir, "README.txt"))
}

func TestUnzipAndPlace_NestedLayout(t *testing.T) {
	dir := t.TempDir()
	zipPath := filepath.Join(dir, "archive.zip")
	// Zip wraps everything in an extra "Ashen_Era_Archive/" folder, as the
	// README says some unzip tools do.
	writeZip(t, zipPath, []string{
		"Ashen_Era_Archive/wiki/page1.md",
		"Ashen_Era_Archive/codex/vol1.pdf",
		"Ashen_Era_Archive/chronicles/vol1.docx",
		"Ashen_Era_Archive/ephemera/letter1.md",
		"Ashen_Era_Archive/images/plate.png",
	})

	extractDir := filepath.Join(dir, "extract")
	if err := unzip(zipPath, extractDir); err != nil {
		t.Fatal(err)
	}
	src, err := findWikiParent(extractDir)
	if err != nil {
		t.Fatal(err)
	}
	wantSrc := filepath.Join(extractDir, "Ashen_Era_Archive")
	if src != wantSrc {
		t.Errorf("nested layout: expected src %s, got %s", wantSrc, src)
	}

	dataDir := filepath.Join(dir, "data", "Ashen_Era_Archive")
	if err := moveDirContents(src, dataDir); err != nil {
		t.Fatal(err)
	}
	if !archivePresent(dataDir) {
		t.Fatal("expected all 5 subdirs present after placement")
	}
	assertFile(t, filepath.Join(dataDir, "wiki", "page1.md"))
	// The extra wrapper folder itself must not appear in the destination.
	if _, err := os.Stat(filepath.Join(dataDir, "Ashen_Era_Archive")); err == nil {
		t.Error("nested wrapper folder should not be copied into dataDir")
	}
}

func TestFindWikiParent_Missing(t *testing.T) {
	dir := t.TempDir()
	if err := os.MkdirAll(filepath.Join(dir, "not-the-archive"), 0o755); err != nil {
		t.Fatal(err)
	}
	if _, err := findWikiParent(dir); err == nil {
		t.Fatal("expected an error when no wiki/ folder is present anywhere")
	}
}

func TestArchivePresent(t *testing.T) {
	dir := t.TempDir()
	if archivePresent(dir) {
		t.Fatal("empty dir should not count as present")
	}
	for _, sub := range archiveSubdirs {
		if err := os.MkdirAll(filepath.Join(dir, sub), 0o755); err != nil {
			t.Fatal(err)
		}
	}
	if !archivePresent(dir) {
		t.Fatal("dir with all subdirs should count as present")
	}
}

func TestFilterEnv(t *testing.T) {
	in := []string{"PATH=/usr/bin", "PYTHONPATH=/opt/ros/humble", "HOME=/home/x"}
	out := filterEnv(in, "PYTHONPATH")
	for _, kv := range out {
		if kv == "PYTHONPATH=/opt/ros/humble" || len(kv) >= 11 && kv[:11] == "PYTHONPATH=" {
			t.Errorf("PYTHONPATH leaked through: %v", out)
		}
	}
	if len(out) != 2 {
		t.Errorf("expected 2 remaining vars, got %d: %v", len(out), out)
	}
}
