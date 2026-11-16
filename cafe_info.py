"""카페 소개 값 받기 — 로그인 없이 보이는 두 화면만 연다.
1) CafeGateInfo.json (카페 번호 · 대표카페(powerCafe) · 회원 수 · 만든 날 · 공개 여부)
2) CafeProfileView.nhn (카페 소개 표: 주제 · 랭킹 단계 · 전체 게시글 · 총 방문자 · 앱 추가 수 · 지식iN 답변 · 스탭 수)
사람 속도로: 요청 사이 1.2~2.0초. 403/429 가 5번 이어지면 멈춘다.
"""
import argparse, json, random, re, sys, time
from datetime import datetime, timezone

from curl_cffi import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
GATE = "https://apis.naver.com/cafe-web/cafe2/CafeGateInfo.json?cluburl={u}"
PROF = "https://cafe.naver.com/CafeProfileView.nhn?clubid={i}"


def strip(t):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    t = t.replace("&nbsp;", " ").replace("&gt;", ">").replace("&amp;", "&")
    return re.sub(r"\s+", " ", t).strip()


def num(pat, t):
    m = re.search(pat, t)
    return int(m.group(1).replace(",", "")) if m else ""


def parse_profile(html):
    t = strip(html)
    out = {}
    m = re.search(r"주제 (.+?) 카페 설명", t)
    out["주제"] = m.group(1).strip() if m else ""
    m = re.search(r"현재랭킹 : (\S+)", t)
    out["랭킹 단계"] = m.group(1) if m else ""
    m = re.search(r'ico_rank rank(\d+)', html)
    out["랭킹 번호"] = int(m.group(1)) if m else ""
    out["회원 수(소개 화면)"] = num(r"카페멤버 : ([\d,]+) 명", t)
    out["전체 게시글"] = num(r"전체 게시글 : ([\d,]+) 개", t)
    out["총 방문자"] = num(r"총 방문자 : ([\d,]+) 명", t)
    out["앱 추가 수"] = num(r"앱 추가수 ([\d,]+)회", t)
    out["지식iN 답변"] = num(r"총 답변수는 ([\d,]+)개", t)
    out["지식iN 채택"] = num(r"이 중 ([\d,]+)개의 답변이 채택", t)
    m = re.search(r"Since (\d{4})\.(\d{2})\.(\d{2})", t)
    out["설립일"] = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""
    m = re.search(r"스탭 : .*? 외 (\d+)명", t)
    out["스탭 외 수"] = int(m.group(1)) if m else ""
    m = re.search(r"카페 성격 (\S+)", t)
    out["카페 성격"] = m.group(1) if m else ""
    m = re.search(r"가입 방식 (.+?) 카페 활동", t)
    out["가입 방식"] = m.group(1).strip() if m else ""
    m = re.search(r"카페 검색어 (.+?) 카페 성격", t)
    out["카페 검색어"] = m.group(1).replace(" , ", ",").strip() if m else ""
    return out


def get(s, url, ref):
    r = s.get(url, headers={"User-Agent": UA, "Referer": ref, "Accept-Language": "ko-KR,ko;q=0.9"},
              impersonate="chrome", timeout=20)
    return r.status_code, r.content


def one(s, u):
    row = {"카페 주소 이름": u, "받은 시각": datetime.now(timezone.utc).isoformat(timespec="seconds"), "확인 불가 까닭": ""}
    code, body = get(s, GATE.format(u=u), "https://cafe.naver.com/")
    if code != 200:
        row["확인 불가 까닭"] = f"게이트 응답 {code}"
        return row, code
    try:
        res = json.loads(body.decode("utf-8"))["message"]["result"]
        v = res["cafeInfoView"]
    except Exception:
        row["확인 불가 까닭"] = "게이트 응답에 카페 정보 없음(없는 카페 · 닫힌 카페)"
        return row, code
    row.update({
        "카페 번호": v.get("cafeId", ""), "카페 이름": v.get("cafeName", ""),
        "대표카페(powerCafe)": v.get("powerCafe", ""), "회원 수": res.get("memberCount", ""),
        "공개(openType)": v.get("openType", ""), "휴면": v.get("dormantCafe", ""),
        "지역카페": v.get("townCafe", ""), "카페 종류": v.get("cafeType", ""),
        "openDate": v.get("openDate", ""),
    })
    time.sleep(random.uniform(1.2, 2.0))
    code2, body2 = get(s, PROF.format(i=v.get("cafeId")), f"https://cafe.naver.com/{u}")
    if code2 != 200:
        row["확인 불가 까닭"] = f"소개 화면 응답 {code2}"
        return row, code2
    html = body2.decode("cp949", "replace")
    p = parse_profile(html)
    if not p["랭킹 단계"] and not p["주제"]:
        row["확인 불가 까닭"] = "소개 화면에 표 없음(비공개 · 로그인 필요로 짐작)"
    row.update(p)
    return row, 200


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    targets = json.load(open(a.targets, encoding="utf-8"))
    s = requests.Session()
    blocks = 0
    with open(a.out, "a", encoding="utf-8") as f:
        for k, u in enumerate(targets, 1):
            try:
                row, code = one(s, u)
            except Exception as e:
                row, code = {"카페 주소 이름": u, "확인 불가 까닭": f"오류 {type(e).__name__}"}, 0
            f.write(json.dumps(row, ensure_ascii=False) + "\n"); f.flush()
            blocks = blocks + 1 if code in (403, 429) else 0
            print(k, u, row.get("랭킹 단계", ""), row.get("확인 불가 까닭", ""), flush=True)
            if blocks >= 5:
                print("네이버가 5번 이어 막음 — 멈춤", file=sys.stderr)
                break
            time.sleep(random.uniform(1.2, 2.0))


if __name__ == "__main__":
    main()
