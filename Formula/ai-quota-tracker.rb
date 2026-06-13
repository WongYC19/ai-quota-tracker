class AiQuotaTracker < Formula
  desc "Multi-provider AI quota tracker with unified dashboard for Antigravity, Codex, and Gemini"
  homepage "https://github.com/WongYC19/ai-quota-tracker"
  url "https://github.com/WongYC19/ai-quota-tracker/archive/refs/heads/main.tar.gz"
  version "1.0.0"
  license "MIT"

  depends_on "python@3.12"
  depends_on "uv"

  def install
    # Create a virtualenv and install dependencies via uv
    system "uv", "pip", "install", "--system",
      "psutil>=5.9.8",
      "requests>=2.32.3",
      "urllib3>=2.3.0",
      "python-dateutil>=2.9.0",
      "pytz>=2024.2"

    # Install application files
    libexec.install "src", "pyproject.toml"

    # Create a launcher script
    (bin/"ai-quota-tracker").write <<~EOS
      #!/bin/bash
      cd "#{libexec}"
      exec python3 src/orchestrator.py "$@"
    EOS
  end

  def post_install
    (var/"ai-quota-tracker").mkpath
    # Symlink the SQLite database into a writable var directory
    (libexec/"tracker_history.db").unlink if (libexec/"tracker_history.db").exist?
    (libexec/"tracker_history.db").make_relative_symlink(var/"ai-quota-tracker/tracker_history.db")
  end

  test do
    # Smoke test: verify the module is importable
    system "python3", "-c", "import sys; sys.path.insert(0, '#{libexec}'); from src import orchestrator; print('OK')"
  end
end
