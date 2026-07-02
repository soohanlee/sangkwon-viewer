import { useEffect, useMemo, useState } from "react";
import {
  api,
  type TableMeta,
  type DataResponse,
  type OptionItem,
  type Summary,
} from "./api";

const REGION_BADGE: Record<string, string> = {
  gangnam: "강남구",
  seongnam: "성남시",
};

export default function App() {
  const [tables, setTables] = useState<TableMeta[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [active, setActive] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.tables(), api.summary()])
      .then(([t, s]) => {
        setTables(t);
        setSummary(s);
        if (t.length) setActive(t[0].name);
      })
      .catch((e) => setError(String(e.message || e)));
  }, []);

  const activeMeta = useMemo(
    () => tables.find((t) => t.name === active),
    [tables, active]
  );

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">📍</span>
          <div>
            <h1>상권분석 데이터 뷰어</h1>
            <p>공공데이터 수집 결과 · 강남구 / 성남시</p>
          </div>
        </div>
      </header>

      {error && <div className="error-banner">⚠ {error}</div>}

      {summary && <Dashboard summary={summary} />}

      <nav className="tabs">
        {tables.map((t) => (
          <button
            key={t.name}
            className={"tab" + (t.name === active ? " active" : "")}
            onClick={() => setActive(t.name)}
          >
            <span className="tab-icon">{t.icon}</span>
            <span>{t.label}</span>
            <span className="tab-count">{t.count.toLocaleString()}</span>
          </button>
        ))}
      </nav>

      {activeMeta && <TableView key={activeMeta.name} meta={activeMeta} />}
    </div>
  );
}

function Dashboard({ summary }: { summary: Summary }) {
  const maxRegion = Math.max(...summary.by_region.map((r) => r.count), 1);
  const maxIndustry = Math.max(...summary.by_industry.map((r) => r.count), 1);
  return (
    <section className="dashboard">
      <div className="panel">
        <h3>지역별 상가업소</h3>
        <div className="bars">
          {summary.by_region.map((r) => (
            <div className="bar-row" key={r.key}>
              <span className="bar-label">{r.label}</span>
              <div className="bar-track">
                <div
                  className="bar-fill region"
                  style={{ width: `${(r.count / maxRegion) * 100}%` }}
                />
              </div>
              <span className="bar-val">{r.count.toLocaleString()}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="panel">
        <h3>업종 대분류 TOP 10</h3>
        <div className="bars">
          {summary.by_industry.map((r) => (
            <div className="bar-row" key={r.label}>
              <span className="bar-label">{r.label}</span>
              <div className="bar-track">
                <div
                  className="bar-fill industry"
                  style={{ width: `${(r.count / maxIndustry) * 100}%` }}
                />
              </div>
              <span className="bar-val">{r.count.toLocaleString()}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function TableView({ meta }: { meta: TableMeta }) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [q, setQ] = useState("");
  const [qInput, setQInput] = useState("");
  const [selects, setSelects] = useState<Record<string, string[]>>({});
  const [ranges, setRanges] = useState<Record<string, { min?: string; max?: string }>>({});
  const [sort, setSort] = useState(meta.sort.col);
  const [order, setOrder] = useState(meta.sort.order);

  const [optionsMap, setOptionsMap] = useState<Record<string, OptionItem[]>>({});
  const [resp, setResp] = useState<DataResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 셀렉트 필터 옵션 로드
  useEffect(() => {
    const selCols = meta.filters.filter((f) => f.type === "select").map((f) => f.col);
    Promise.all(selCols.map((c) => api.options(meta.name, c)))
      .then((lists) => {
        const m: Record<string, OptionItem[]> = {};
        selCols.forEach((c, i) => (m[c] = lists[i]));
        setOptionsMap(m);
      })
      .catch(() => {});
  }, [meta.name]);

  // 데이터 조회
  useEffect(() => {
    const params = new URLSearchParams();
    params.set("page", String(page));
    params.set("page_size", String(pageSize));
    params.set("sort", sort);
    params.set("order", order);
    if (q) params.set("q", q);
    Object.entries(selects).forEach(([col, vals]) =>
      vals.forEach((v) => params.append(col, v))
    );
    Object.entries(ranges).forEach(([col, r]) => {
      if (r.min) params.set(`${col}__min`, r.min);
      if (r.max) params.set(`${col}__max`, r.max);
    });
    setLoading(true);
    setError(null);
    api
      .data(meta.name, params)
      .then(setResp)
      .catch((e) => setError(String(e.message || e)))
      .finally(() => setLoading(false));
  }, [meta.name, page, pageSize, sort, order, q, selects, ranges]);

  const activeFilterCount =
    Object.values(selects).reduce((n, v) => n + v.length, 0) +
    Object.values(ranges).filter((r) => r.min || r.max).length +
    (q ? 1 : 0);

  function toggleSelect(col: string, value: string) {
    setPage(1);
    setSelects((prev) => {
      const cur = prev[col] || [];
      const next = cur.includes(value)
        ? cur.filter((v) => v !== value)
        : [...cur, value];
      const copy = { ...prev };
      if (next.length) copy[col] = next;
      else delete copy[col];
      return copy;
    });
  }

  function setRange(col: string, key: "min" | "max", value: string) {
    setPage(1);
    setRanges((prev) => ({ ...prev, [col]: { ...prev[col], [key]: value } }));
  }

  function resetFilters() {
    setSelects({});
    setRanges({});
    setQ("");
    setQInput("");
    setPage(1);
  }

  function toggleSort(col: string) {
    if (sort === col) setOrder(order === "asc" ? "desc" : "asc");
    else {
      setSort(col);
      setOrder("asc");
    }
    setPage(1);
  }

  return (
    <div className="tableview">
      <aside className="filters">
        <div className="filters-head">
          <h3>필터</h3>
          {activeFilterCount > 0 && (
            <button className="reset" onClick={resetFilters}>
              초기화 ({activeFilterCount})
            </button>
          )}
        </div>

        {meta.search.length > 0 && (
          <div className="filter-group">
            <label>검색</label>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                setPage(1);
                setQ(qInput.trim());
              }}
            >
              <input
                className="search-input"
                placeholder="상호명·주소 등"
                value={qInput}
                onChange={(e) => setQInput(e.target.value)}
              />
            </form>
          </div>
        )}

        {meta.filters
          .filter((f) => f.type === "select")
          .map((f) => (
            <div className="filter-group" key={f.col}>
              <label>{f.label}</label>
              <div className="chips">
                {(optionsMap[f.col] || []).slice(0, 60).map((o) => {
                  const on = (selects[f.col] || []).includes(o.value);
                  return (
                    <button
                      key={o.value}
                      className={"chip" + (on ? " on" : "")}
                      onClick={() => toggleSelect(f.col, o.value)}
                      title={`${o.label} (${o.count.toLocaleString()})`}
                    >
                      {o.label}
                      <span className="chip-count">{o.count.toLocaleString()}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}

        {meta.filters
          .filter((f) => f.type === "range")
          .map((f) => (
            <div className="filter-group" key={f.col}>
              <label>{f.label}</label>
              <div className="range">
                <input
                  type="number"
                  placeholder="최소"
                  value={ranges[f.col]?.min ?? ""}
                  onChange={(e) => setRange(f.col, "min", e.target.value)}
                />
                <span>~</span>
                <input
                  type="number"
                  placeholder="최대"
                  value={ranges[f.col]?.max ?? ""}
                  onChange={(e) => setRange(f.col, "max", e.target.value)}
                />
              </div>
            </div>
          ))}
      </aside>

      <main className="results">
        <div className="results-head">
          <div className="result-count">
            {loading ? (
              "불러오는 중…"
            ) : resp ? (
              <>
                총 <strong>{resp.total.toLocaleString()}</strong>건
                {activeFilterCount > 0 && " (필터 적용됨)"}
              </>
            ) : (
              ""
            )}
          </div>
          <div className="page-size">
            <label>표시</label>
            <select
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value));
                setPage(1);
              }}
            >
              {[25, 50, 100, 200].map((n) => (
                <option key={n} value={n}>
                  {n}행
                </option>
              ))}
            </select>
          </div>
        </div>

        {error && <div className="error-banner">⚠ {error}</div>}

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {meta.columns.map((c) => (
                  <th
                    key={c.col}
                    className={
                      (c.numeric ? "num " : "") + (sort === c.col ? "sorted" : "")
                    }
                    onClick={() => toggleSort(c.col)}
                  >
                    {c.label}
                    {sort === c.col && (
                      <span className="arrow">{order === "asc" ? " ▲" : " ▼"}</span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {resp?.rows.map((row, i) => (
                <tr key={i}>
                  {meta.columns.map((c) => (
                    <td key={c.col} className={c.numeric ? "num" : ""}>
                      {renderCell(c.col, row)}
                    </td>
                  ))}
                </tr>
              ))}
              {resp && resp.rows.length === 0 && !loading && (
                <tr>
                  <td className="empty" colSpan={meta.columns.length}>
                    조건에 맞는 데이터가 없습니다.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {resp && resp.pages > 1 && (
          <Pager page={page} pages={resp.pages} onChange={setPage} />
        )}
      </main>
    </div>
  );
}

function renderCell(col: string, row: Record<string, any>) {
  const v = row[col];
  if (v === null || v === undefined || v === "") return <span className="muted">—</span>;
  if (col === "region_key") {
    const label = row._region_label || REGION_BADGE[v] || v;
    return <span className={`region-badge ${v}`}>{label}</span>;
  }
  if (typeof v === "number") return v.toLocaleString();
  return String(v);
}

function Pager({
  page,
  pages,
  onChange,
}: {
  page: number;
  pages: number;
  onChange: (p: number) => void;
}) {
  const window = 2;
  const nums: number[] = [];
  for (let i = Math.max(1, page - window); i <= Math.min(pages, page + window); i++)
    nums.push(i);
  return (
    <div className="pager">
      <button disabled={page <= 1} onClick={() => onChange(1)}>
        «
      </button>
      <button disabled={page <= 1} onClick={() => onChange(page - 1)}>
        ‹
      </button>
      {nums[0] > 1 && <span className="dots">…</span>}
      {nums.map((n) => (
        <button
          key={n}
          className={n === page ? "current" : ""}
          onClick={() => onChange(n)}
        >
          {n}
        </button>
      ))}
      {nums[nums.length - 1] < pages && <span className="dots">…</span>}
      <button disabled={page >= pages} onClick={() => onChange(page + 1)}>
        ›
      </button>
      <button disabled={page >= pages} onClick={() => onChange(pages)}>
        »
      </button>
      <span className="page-info">
        {page} / {pages}
      </span>
    </div>
  );
}
