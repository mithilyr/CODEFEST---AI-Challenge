// setup.exe: auto-setup for the Ashen Era Archive Assistant on Windows.
//
// A single static binary (no Python needed to run *this*) that finds a
// Python 3.11+ interpreter, creates the project venv, installs
// dependencies, downloads and unpacks the archive if it isn't already
// there, writes .env, verifies integrity, and starts the web app.
//
// Built with: GOOS=windows GOARCH=amd64 go build -o setup.exe .
package main

import (
	"archive/zip"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
)

const archiveURL = "https://benchdata792fda32.blob.core.windows.net/codefest2026/Ashen_Era_Archive.zip"

var archiveSubdirs = []string{"chronicles", "codex", "ephemera", "images", "wiki"}

func logStep(format string, args ...any) {
	fmt.Printf("\n==> "+format+"\n", args...)
}

func fatal(err error) {
	fmt.Fprintln(os.Stderr, "\nerror:", err)
	fmt.Println("\nPress Enter to close...")
	fmt.Scanln()
	os.Exit(1)
}

func main() {
	noRun := false
	for _, arg := range os.Args[1:] {
		if arg == "--no-run" {
			noRun = true
		} else {
			fatal(fmt.Errorf("unknown flag: %s", arg))
		}
	}

	root, err := projectRoot()
	if err != nil {
		fatal(err)
	}
	if err := os.Chdir(root); err != nil {
		fatal(fmt.Errorf("cd into %s: %w", root, err))
	}
	fmt.Printf("Ashen Era Archive Assistant - Windows setup\nProject root: %s\n", root)

	pyExe, pyArgs, err := findPython311()
	if err != nil {
		fatal(err)
	}
	fmt.Printf("using %s\n", strings.Join(append([]string{pyExe}, pyArgs...), " "))

	venvPy := filepath.Join(root, ".venv", "Scripts", "python.exe")
	if _, err := os.Stat(venvPy); errors.Is(err, os.ErrNotExist) {
		logStep("Creating virtual environment (.venv)")
		if err := run(root, pyExe, append(pyArgs, "-m", "venv", ".venv")...); err != nil {
			fatal(err)
		}
	} else {
		logStep("Virtual environment already exists")
	}

	logStep("Installing dependencies")
	if err := run(root, venvPy, "-m", "pip", "install", "-q", "--upgrade", "pip"); err != nil {
		fatal(err)
	}
	if err := run(root, venvPy, "-m", "pip", "install", "-q", "-r", "requirements.txt"); err != nil {
		fatal(err)
	}

	envPath := filepath.Join(root, ".env")
	if _, err := os.Stat(envPath); errors.Is(err, os.ErrNotExist) {
		logStep("Creating .env from .env.example")
		if err := copyFile(filepath.Join(root, ".env.example"), envPath); err != nil {
			fatal(err)
		}
	} else {
		logStep(".env already exists, leaving it alone")
	}

	dataDir := filepath.Join(root, "data", "Ashen_Era_Archive")
	if !archivePresent(dataDir) {
		if err := downloadAndExtractArchive(root, dataDir); err != nil {
			fatal(err)
		}
	} else {
		logStep("Archive already present at data\\Ashen_Era_Archive")
	}

	logStep("Verifying archive integrity")
	if err := run(root, venvPy, "-m", "src.ingest.integrity"); err != nil {
		fatal(err)
	}

	if noRun {
		logStep("Setup complete. Start the app with: .venv\\Scripts\\python.exe -m src.ui.server")
		return
	}

	logStep("Starting the app on http://127.0.0.1:8000 (Ctrl-C to stop)")
	if err := run(root, venvPy, "-m", "src.ui.server"); err != nil {
		fatal(err)
	}
}

// projectRoot returns the directory containing this executable, which is
// expected to sit next to requirements.txt in the project root.
func projectRoot() (string, error) {
	exePath, err := os.Executable()
	if err != nil {
		return "", err
	}
	exePath, err = filepath.EvalSymlinks(exePath)
	if err != nil {
		return "", err
	}
	dir := filepath.Dir(exePath)
	if _, err := os.Stat(filepath.Join(dir, "requirements.txt")); err == nil {
		return dir, nil
	}
	// Fall back to the current working directory, for `go run` and for
	// running the exe from elsewhere with the project as cwd.
	cwd, err := os.Getwd()
	if err != nil {
		return "", err
	}
	if _, err := os.Stat(filepath.Join(cwd, "requirements.txt")); err == nil {
		return cwd, nil
	}
	return "", fmt.Errorf("could not find requirements.txt next to setup.exe or in the current directory - run setup.exe from inside the project folder")
}

// findPython311 looks for a Python 3.11+ interpreter via the `py` launcher
// first (the standard way to select a version on Windows), then falls back
// to whatever `python`/`python3` resolve to on PATH. Returns the program to
// run plus any leading selector args (e.g. "py", ["-3.11"]).
func findPython311() (string, []string, error) {
	type candidate struct {
		exe  string
		args []string
	}
	candidates := []candidate{
		{"py", []string{"-3.13"}},
		{"py", []string{"-3.12"}},
		{"py", []string{"-3.11"}},
		{"python", nil},
		{"python3", nil},
	}
	for _, c := range candidates {
		exe, err := exec.LookPath(c.exe)
		if err != nil {
			continue
		}
		checkArgs := append(append([]string{}, c.args...), "-c",
			`import sys; print("%d.%d" % sys.version_info[:2])`)
		out, err := exec.Command(exe, checkArgs...).Output()
		if err != nil {
			continue
		}
		ver := strings.TrimSpace(string(out))
		parts := strings.SplitN(ver, ".", 2)
		if len(parts) != 2 {
			continue
		}
		major, err1 := strconv.Atoi(parts[0])
		minor, err2 := strconv.Atoi(parts[1])
		if err1 != nil || err2 != nil || major != 3 || minor < 11 {
			continue
		}
		return exe, c.args, nil
	}
	return "", nil, errors.New(
		"no Python 3.11+ interpreter found.\n" +
			"Install one from https://www.python.org/downloads/ (check " +
			"\"Add python.exe to PATH\" during install) and run setup.exe again.")
}

// run executes a program directly (no shell, no string-splitting - the
// project path itself contains spaces), with PYTHONPATH cleared so a Python
// install elsewhere on the machine can't leak unrelated packages into this
// venv.
func run(dir, exe string, args ...string) error {
	cmd := exec.Command(exe, args...)
	cmd.Dir = dir
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.Env = filterEnv(os.Environ(), "PYTHONPATH")
	return cmd.Run()
}

func filterEnv(env []string, dropKey string) []string {
	out := make([]string, 0, len(env))
	prefix := dropKey + "="
	for _, kv := range env {
		if !strings.HasPrefix(kv, prefix) {
			out = append(out, kv)
		}
	}
	return out
}

func copyFile(src, dst string) error {
	data, err := os.ReadFile(src)
	if err != nil {
		return err
	}
	return os.WriteFile(dst, data, 0o644)
}

func archivePresent(dataDir string) bool {
	for _, sub := range archiveSubdirs {
		info, err := os.Stat(filepath.Join(dataDir, sub))
		if err != nil || !info.IsDir() {
			return false
		}
	}
	return true
}

func downloadAndExtractArchive(root, dataDir string) error {
	logStep("Downloading the Ashen Era Archive (~123 MB)")
	tmpZip, err := os.CreateTemp("", "ashen_era_archive_*.zip")
	if err != nil {
		return err
	}
	tmpZipPath := tmpZip.Name()
	defer os.Remove(tmpZipPath)

	resp, err := http.Get(archiveURL)
	if err != nil {
		tmpZip.Close()
		return fmt.Errorf("downloading archive: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		tmpZip.Close()
		return fmt.Errorf("downloading archive: HTTP %s", resp.Status)
	}
	written, err := io.Copy(tmpZip, resp.Body)
	closeErr := tmpZip.Close()
	if err != nil {
		return fmt.Errorf("downloading archive: %w", err)
	}
	if closeErr != nil {
		return closeErr
	}
	fmt.Printf("downloaded %.1f MB\n", float64(written)/1024/1024)

	logStep("Extracting archive")
	tmpDir, err := os.MkdirTemp("", "ashen_era_archive_extract_*")
	if err != nil {
		return err
	}
	defer os.RemoveAll(tmpDir)

	if err := unzip(tmpZipPath, tmpDir); err != nil {
		return fmt.Errorf("extracting archive: %w", err)
	}

	// The zip may or may not wrap its contents in an extra top-level
	// folder. Find whichever directory actually holds `wiki/` and use
	// that as the source, so both layouts land in the same place.
	src, err := findWikiParent(tmpDir)
	if err != nil {
		return err
	}

	if err := os.RemoveAll(dataDir); err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(dataDir), 0o755); err != nil {
		return err
	}
	if err := moveDirContents(src, dataDir); err != nil {
		return err
	}
	return nil
}

func unzip(zipPath, destDir string) error {
	r, err := zip.OpenReader(zipPath)
	if err != nil {
		return err
	}
	defer r.Close()

	for _, f := range r.File {
		targetPath := filepath.Join(destDir, f.Name)
		if !strings.HasPrefix(targetPath, filepath.Clean(destDir)+string(os.PathSeparator)) {
			return fmt.Errorf("illegal file path in archive: %s", f.Name)
		}
		if f.FileInfo().IsDir() {
			if err := os.MkdirAll(targetPath, 0o755); err != nil {
				return err
			}
			continue
		}
		if err := os.MkdirAll(filepath.Dir(targetPath), 0o755); err != nil {
			return err
		}
		if err := extractOne(f, targetPath); err != nil {
			return err
		}
	}
	return nil
}

func extractOne(f *zip.File, targetPath string) error {
	rc, err := f.Open()
	if err != nil {
		return err
	}
	defer rc.Close()

	out, err := os.OpenFile(targetPath, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, f.Mode())
	if err != nil {
		return err
	}
	defer out.Close()

	_, err = io.Copy(out, rc)
	return err
}

func findWikiParent(root string) (string, error) {
	if info, err := os.Stat(filepath.Join(root, "wiki")); err == nil && info.IsDir() {
		return root, nil
	}
	var found string
	err := filepath.WalkDir(root, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() && d.Name() == "wiki" {
			found = filepath.Dir(path)
			return filepath.SkipAll
		}
		return nil
	})
	if err != nil {
		return "", err
	}
	if found == "" {
		return "", errors.New("could not find the archive's 'wiki' folder after extraction")
	}
	return found, nil
}

// moveDirContents moves everything in src into dst. Prefers a rename (fast,
// atomic); falls back to copy-then-delete when src and dst are on different
// volumes (e.g. TEMP on C:, project on D:), where Windows refuses a rename.
func moveDirContents(src, dst string) error {
	if err := os.MkdirAll(dst, 0o755); err != nil {
		return err
	}
	entries, err := os.ReadDir(src)
	if err != nil {
		return err
	}
	for _, e := range entries {
		from := filepath.Join(src, e.Name())
		to := filepath.Join(dst, e.Name())
		if err := os.Rename(from, to); err != nil {
			if err := copyTree(from, to); err != nil {
				return err
			}
		}
	}
	return nil
}

func copyTree(src, dst string) error {
	return filepath.WalkDir(src, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		rel, err := filepath.Rel(src, path)
		if err != nil {
			return err
		}
		target := filepath.Join(dst, rel)
		if d.IsDir() {
			return os.MkdirAll(target, 0o755)
		}
		info, err := d.Info()
		if err != nil {
			return err
		}
		if err := copyFile(path, target); err != nil {
			return err
		}
		return os.Chmod(target, info.Mode())
	})
}
