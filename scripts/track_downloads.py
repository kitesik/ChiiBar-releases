"""Record public release ZIP download counters; Python standard library only."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

REPO = "kitesik/ChiiBar-releases"
KST = timezone(timedelta(hours=9))


def fetch_releases():
    releases = []
    for page in range(1, 1001):
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "ChiiBar-download-tracker"}
        if os.environ.get("GH_TOKEN"):
            headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
        request = Request(f"https://api.github.com/repos/{REPO}/releases?per_page=100&page={page}", headers=headers)
        with urlopen(request, timeout=30) as response:
            batch = json.load(response)
        if not isinstance(batch, list):
            raise ValueError("Unexpected releases response")
        releases.extend(batch)
        if len(batch) < 100:
            return releases
    raise ValueError("Too many release pages; refusing partial results")


def snapshot(releases, now):
    assets = []
    for release in releases:
        if release["draft"]:
            continue
        for asset in release["assets"]:
            if asset["name"] != "ChiiBar-macOS.zip":
                continue
            count = asset["download_count"]
            if type(count) is not int or count < 0:
                raise ValueError("Invalid download count")
            assets.append({"id": asset["id"], "version": release["tag_name"], "downloads": count})
    if not assets or len({a["id"] for a in assets}) != len(assets):
        raise ValueError("Missing or duplicate app assets; refusing to overwrite history")
    return {"collected_at": now.astimezone(KST).isoformat(timespec="seconds"), "assets": assets}


def total(item):
    return sum(a["downloads"] for a in item["assets"])


def increase(previous, current):
    old = {a["id"]: a["downloads"] for a in previous["assets"]}
    new = {a["id"]: a["downloads"] for a in current["assets"]}
    if old.keys() - new.keys() or any(new[k] < old[k] for k in old.keys() & new.keys()):
        return None  # Asset deletion/replacement/reset must not look like user churn.
    return sum(value - old.get(key, 0) for key, value in new.items())


def render(history):
    latest = history[-1]
    lines = ["# 치이바 다운로드 통계", "",
             f"마지막 수집: {latest['collected_at']} (한국 시간)", "",
             f"**현재 공개된 앱 ZIP의 누적 다운로드: {total(latest):,}회**", "",
             "다운로드 횟수이며 고유 인원·설치·실행 수가 아닙니다. 재다운로드, 업데이트, 개발자 테스트도 포함됩니다.", "",
             "## 버전별 다운로드", "", "| 버전 | 횟수 |", "|---|---:|"]
    for asset in latest["assets"]:
        version = asset["version"].replace("|", "\\|").replace("\n", " ").replace("\r", " ")
        lines.append(f"| {version} | {asset['downloads']:,} |")
    lines += ["", "## 날짜별 관측", "", "하루의 마지막 수집값을 보관합니다. 증가량은 직전 관측과의 차이로, 수집 시각 사이의 다운로드입니다.",
              "첫 관측 이전의 날짜별 내역은 복원할 수 없습니다. 누락일이 있으면 증가량에는 그 기간이 함께 포함됩니다.", "",
              "| 한국 날짜 | 공개 ZIP 누적 | 전 관측 대비 증가 |", "|---|---:|---:|"]
    rows = []
    for index, item in enumerate(history):
        delta = "기준점"
        if index:
            value = increase(history[index - 1], item)
            delta = "비교 불가 (파일 삭제·교체·초기화)" if value is None else f"+{value:,}"
        rows.append(f"| {item['collected_at'][:10]} | {total(item):,} | {delta} |")
    lines += list(reversed(rows))
    lines += ["", "## 수집 방법", "",
              "- 매일 한국 시간 오전 8시 17분경 GitHub Actions에서 수집합니다. 실행이 지연될 수 있습니다.",
              "- `ChiiBar-macOS.zip`만 셉니다. 체크섬과 소스 압축 파일은 제외합니다.",
              "- [원본 기록](snapshots/)에는 파일 ID와 버전별 횟수, 수집 시각이 남습니다. 같은 날짜 재실행은 해당 날짜만 갱신합니다.",
              "- 삭제된 배포 파일은 현재 합계에서 빠지지만 과거 기록은 보존됩니다. 파일 ID 변경·카운터 감소가 있으면 해당 구간 증가량은 비교 불가로 표시합니다.",
              "- [수집 작업](https://github.com/kitesik/ChiiBar-releases/actions/workflows/download-stats.yml)에서 Run workflow로 수동 실행할 수 있습니다.",
              "- GitHub의 공개 저장소 예약 실행은 60일간 저장소 활동이 없으면 비활성화될 수 있습니다. 그 경우 수집 작업을 다시 활성화하세요.",
              "- 앱이나 사용자 기기에서 개인정보를 수집하지 않습니다. GitHub의 공개 집계값만 읽습니다.", "",
              "[GitHub API 문서](https://docs.github.com/en/rest/releases/assets) · [예약 실행 안내](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)", ""]
    return "\n".join(lines)


def save(root, current):
    directory = root / "stats" / "snapshots"
    history = {}
    if directory.exists():
        history = {p.stem: json.loads(p.read_text()) for p in sorted(directory.glob("*.json"))}
    day = current["collected_at"][:10]
    history[day] = current
    report = render([history[key] for key in sorted(history)])
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{day}.json").write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (root / "stats" / "README.md").write_text(report, encoding="utf-8")
    print(f"{day}: {total(current)} downloads across {len(current['assets'])} app assets")


if __name__ == "__main__":
    save(Path(__file__).resolve().parents[1], snapshot(fetch_releases(), datetime.now(KST)))
