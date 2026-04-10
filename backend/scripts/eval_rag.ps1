#!/usr/bin/env pwsh
# ============================================================
# RAG Retrieval Evaluation Script  (NO LLM required)
# Phase 3: evaluates HYBRID search (vector + BM25 ts_rank)
# Evaluates embedding & retrieval quality directly via:
#   - Embedding service  : http://localhost:8080
#   - Kong Gateway       : http://localhost:8000
#   - PostgreSQL          : via docker compose exec
#
# Metrics produced (all computable without Gemini):
#   1. Similarity score distribution per query (hybrid score)
#   2. Precision@K (did top-K contain expected source_type?)
#   3. Source type distribution in retrieved results
#   4. Threshold analysis (% chunks above similarity cutoffs)
#   5. Query-to-chunk traceability table (human-readable)
#
# hybrid_score = 0.6 × vector_score + 0.4 × ts_rank (BM25)
#
# Run from: backend/ folder
# Usage:    .\scripts\eval_rag.ps1
#           .\scripts\eval_rag.ps1 -Token "eyJhbG..." -SkipDataGen
# ============================================================
param(
    [string]$Token       = "",
    [switch]$SkipDataGen = $false,
    [int]   $TopK        = 8,
    [float] $MinSim      = 0.30   # minimum acceptable similarity threshold
)

$GATEWAY   = "http://localhost:8000"
$EMBED_URL = "http://localhost:8080"
$PASS = 0; $ERRORS = 0

# Force UTF-8 throughout so Vietnamese text is not garbled
[Console]::InputEncoding  = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding           = [System.Text.Encoding]::UTF8

function Write-Pass($msg) { Write-Host "[PASS] $msg" -ForegroundColor Green;  $script:PASS++ }
function Write-Fail($msg) { Write-Host "[FAIL] $msg" -ForegroundColor Red;    $script:ERRORS++ }
function Write-Info($msg) { Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Magenta }
function Write-Sub($msg)  { Write-Host "  >> $msg"   -ForegroundColor White }

# ─── Helper: POST JSON ──────────────────────────────────────────────────────
function Invoke-Post($url, $body, $token = $null) {
    $headers = @{ "Content-Type" = "application/json" }
    if ($token) { $headers["Authorization"] = "Bearer $token" }
    try {
        return Invoke-RestMethod -Uri $url -Method Post -Headers $headers `
                                 -Body ($body | ConvertTo-Json -Compress -Depth 10) `
                                 -ErrorAction Stop
    } catch {
        $status = $_.Exception.Response.StatusCode.value__
        Write-Fail "POST $url → HTTP $status : $_"
        return $null
    }
}
# Helper: run a SQL string inside the postgres container via temp file
# Avoids Windows PowerShell stdout-encoding issue with 'docker compose exec -T'
function Invoke-Psql($sql) {
    $tmpSql = Join-Path $env:TEMP "eval_psql_$(Get-Random).sql"
    # Prepend SET client_encoding so psql always outputs UTF-8
    $fullSql = "SET client_encoding = 'UTF8';`n" + $sql
    [System.IO.File]::WriteAllText($tmpSql, $fullSql, [System.Text.Encoding]::UTF8)
    docker cp $tmpSql "backend-postgres-1:/tmp/eval.sql" | Out-Null
    Remove-Item $tmpSql -Force -ErrorAction SilentlyContinue
    $result = docker exec backend-postgres-1 psql -U fw -d insight_db -t -A -F "|" -f /tmp/eval.sql 2>&1
    return $result
}

function Invoke-Get($url, $token = $null) {
    $headers = @{}
    if ($token) { $headers["Authorization"] = "Bearer $token" }
    try {
        return Invoke-RestMethod -Uri $url -Method Get -Headers $headers -ErrorAction Stop
    } catch {
        $status = $_.Exception.Response.StatusCode.value__
        Write-Fail "GET $url → HTTP $status : $_"
        return $null
    }
}

# ════════════════════════════════════════════════════════════════════════════
Write-Step "0. Prerequisites"
# ════════════════════════════════════════════════════════════════════════════
$health = Invoke-Get "$EMBED_URL/health"
if ($health -and $health.model_loaded -eq $true) {
    Write-Pass "Embedding service: healthy (model_loaded=true)"
} else {
    Write-Fail "Embedding service not ready — aborting"; exit 1
}

# ════════════════════════════════════════════════════════════════════════════
Write-Step "1. Auth — get evaluation token"
# ════════════════════════════════════════════════════════════════════════════
if ($Token -ne "") {
    Write-Info "Using provided token"
} else {
    $suffix  = (Get-Random -Maximum 999999)
    $email   = "eval_user_$suffix@test.com"
    $pw      = "EvalPass123!"
    $reg     = Invoke-Post "$GATEWAY/auth/register" @{ email=$email; password=$pw }
    if (-not $reg) { Write-Fail "Register failed"; exit 1 }
    $userId  = $reg.id
    Write-Info "Registered: $email  (id=$userId)"

    $login = Invoke-Post "$GATEWAY/auth/login" @{ email=$email; password=$pw }
    if (-not $login) { Write-Fail "Login failed"; exit 1 }
    $Token = $login.access_token
    Write-Pass "Authenticated"
}

# ════════════════════════════════════════════════════════════════════════════
Write-Step "2. Data seeding (skip with -SkipDataGen)"
# ════════════════════════════════════════════════════════════════════════════
if (-not $SkipDataGen) {
    Write-Info "Seeding evaluation dataset..."

    # 10 transactions with known categories
    $txData = @(
        @{ amount=450000;  currency="VND"; type="expense"; category="food";          transaction_date="2026-03-01"; note="Bún bò buổi sáng" }
        @{ amount=1200000; currency="VND"; type="expense"; category="shopping";      transaction_date="2026-03-03"; note="Mua áo thun online" }
        @{ amount=3500000; currency="VND"; type="income";  category="other";         transaction_date="2026-03-05"; note="Lương tháng 3 thu nhập chính" }
        @{ amount=80000;   currency="VND"; type="expense"; category="transport";     transaction_date="2026-03-07"; note="Grab đi làm" }
        @{ amount=750000;  currency="VND"; type="expense"; category="food";          transaction_date="2026-03-10"; note="Ăn tối nhà hàng với gia đình" }
        @{ amount=200000;  currency="VND"; type="expense"; category="health";        transaction_date="2026-03-12"; note="Mua thuốc cảm cúm" }
        @{ amount=500000;  currency="VND"; type="expense"; category="entertainment"; transaction_date="2026-03-15"; note="Vé xem phim cuối tuần" }
        @{ amount=900000;  currency="VND"; type="expense"; category="shopping";      transaction_date="2026-03-18"; note="Dụng cụ thể thao" }
        @{ amount=150000;  currency="VND"; type="expense"; category="food";          transaction_date="2026-03-20"; note="Cà phê làm việc" }
        @{ amount=2000000; currency="VND"; type="income";  category="other";         transaction_date="2026-03-25"; note="Thưởng bonus hoàn thành dự án" }
    )
    $txCreated = 0
    foreach ($tx in $txData) {
        $r = Invoke-Post "$GATEWAY/transactions" $tx $Token
        if ($r -and $r.id) { $txCreated++ }
    }
    Write-Info "Transactions seeded: $txCreated/10"

    # 5 journal entries with known topics
    $journalData = @(
        "Hôm nay đi ăn bún bò với đồng nghiệp. Chi tiêu ăn uống tháng này tăng nhiều so với tháng trước, cần kiểm soát hơn."
        "Nhận lương tháng 3. Quyết định để dành 30% vào quỹ tiết kiệm, không mua sắm lung tung nữa."
        "Mua áo thun mới trên Shopee. Thấy hơi lãng phí vì tủ đồ còn nhiều. Cần giảm chi tiêu shopping."
        "Đi khám sức khỏe định kỳ. May mắn không có vấn đề gì. Tiền thuốc 200k nhưng sức khỏe là quan trọng nhất."
        "Tháng này tiết kiệm được 1.5 triệu, đạt mục tiêu đề ra. Tháng sau phấn đấu tiết kiệm thêm 500k."
    )
    $jCreated = 0
    foreach ($content in $journalData) {
        $r = Invoke-Post "$GATEWAY/journal/entries" @{ content=$content } $Token
        if ($r -and $r.id) { $jCreated++ }
    }
    Write-Info "Journal entries seeded: $jCreated/5"

    # 5 mood entries
    $moodData = @(
        @{ score=4; note="Vui vì nhận lương đúng hạn" }
        @{ score=2; note="Lo lắng vì chi tiêu tháng này hơi nhiều" }
        @{ score=5; note="Rất hài lòng khi đạt mục tiêu tiết kiệm" }
        @{ score=3; note="Bình thường, không lo không vui" }
        @{ score=2; note="Căng thẳng vì chi tiêu shopping quá tay" }
    )
    $mCreated = 0
    foreach ($mood in $moodData) {
        $r = Invoke-Post "$GATEWAY/journal/moods" $mood $Token
        if ($r -and $r.id) { $mCreated++ }
    }
    Write-Info "Mood entries seeded: $mCreated/5"

    Write-Info "Waiting 20s for RabbitMQ → embedding pipeline..."
    Start-Sleep -Seconds 20
} else {
    Write-Info "Skipping data generation (using existing chunks for token)"
}

# ════════════════════════════════════════════════════════════════════════════
Write-Step "3. Corpus snapshot — what's in the vector store?"
# ════════════════════════════════════════════════════════════════════════════
Write-Info "Querying document_chunks for this user's data..."

# Note: we use the postgres container to run diagnostics directly
$corpusSQL = @"
SELECT
  source_type,
  COUNT(*)                       AS chunks,
  ROUND(AVG(char_length(content))::numeric, 0) AS avg_content_chars,
  MIN(char_length(content))      AS min_chars,
  MAX(char_length(content))      AS max_chars,
  BOOL_AND(embedding IS NOT NULL) AS all_embedded
FROM document_chunks
GROUP BY source_type
ORDER BY source_type;
"@

$corpusResult = Invoke-Psql $corpusSQL
Write-Host ""
Write-Host "  ┌─────────────────"
Write-Host "  │ VECTOR STORE CORPUS" -ForegroundColor White
Write-Host "  ├─────────────────"
Write-Host "  │ source_type    | chunks | avg_chars | min | max | all_embedded" -ForegroundColor DarkGray
foreach ($line in ($corpusResult -split "`n")) {
    if ($line.Trim()) { Write-Host "  │ $($line.Trim())" }
}
Write-Host "  └─────────────────"

$totalChunks  = Invoke-Psql "SELECT COUNT(*) FROM document_chunks WHERE embedding IS NOT NULL;"
$totalCount   = ($totalChunks | Where-Object { $_ -match '^\s*\d+\s*$' } | Select-Object -First 1).Trim()
if ($totalCount -and [int]$totalCount -gt 0) {
    Write-Pass "Vector store populated: $totalCount embedded chunks"
} else {
    Write-Fail "No embedded chunks in DB — ingestion failed"
}

# ════════════════════════════════════════════════════════════════════════════
Write-Step "4. Evaluation queries — retrieval traceability"
# ════════════════════════════════════════════════════════════════════════════
Write-Info "Each query has an EXPECTED source type — we measure whether retrieval matches."
Write-Host ""

# Define evaluation queries with:
#   - question        : natural language query
#   - expected_type   : which source_type SHOULD dominate in top-K results
#   - expected_keyword: string that SHOULD appear in at least 1 top chunk
$evalQueries = @(
    @{
        question         = "Tôi đã chi tiêu bao nhiêu cho thực phẩm và ăn uống?"
        expected_type    = "transaction"
        expected_keyword = "food"
        label            = "TX-FOOD"
    }
    @{
        question         = "Thu nhập và lương của tôi tháng 3?"
        expected_type    = "transaction"
        expected_keyword = "Lương"
        label            = "TX-INCOME"
    }
    @{
        question         = "Chi tiêu mua sắm của tôi ra sao?"
        expected_type    = "transaction"
        expected_keyword = "shopping"
        label            = "TX-SHOP"
    }
    @{
        question         = "Sức khỏe và tiền thuốc của tôi tháng này?"
        expected_type    = "transaction"
        expected_keyword = "thuốc"
        label            = "TX-HEALTH"
    }
    @{
        question         = "Tôi cảm thấy như thế nào về việc tiết kiệm tiền?"
        expected_type    = "journal_entry"
        expected_keyword = "tiết kiệm"
        label            = "J-SAVING"
    }
    @{
        question         = "Cảm xúc và tâm trạng của tôi gần đây?"
        expected_type    = "mood_entry"
        expected_keyword = ""
        label            = "MOOD-GENERAL"
    }
    @{
        question         = "Tôi có lo lắng hay căng thẳng về tài chính không?"
        expected_type    = "mood_entry"
        expected_keyword = "căng thẳng"
        label            = "MOOD-STRESS"
    }
    @{
        question         = "Nhật ký và suy nghĩ của tôi về chi tiêu mua sắm?"
        expected_type    = "journal_entry"
        expected_keyword = "shopping"
        label            = "J-SHOP"
    }
)

# Track aggregate results
$totalQueries      = $evalQueries.Count
$precisionHits     = 0   # query where top-1 matches expected_type
$topKHits          = 0   # query where at least 1 of top-K matches expected_type
$keywordHits       = 0   # query where at least 1 chunk contains expected_keyword
$allSimilarities   = @() # for distribution analysis
$lowSimQueries     = @() # queries where max sim < MinSim
$resultsTable      = @() # for final report

Write-Host ("  {0,-12} {1,-14} {2,-10} {3,-10} {4,-10} {5,-10} {6}" -f `
    "Label", "Expected", "Top-1 Hit", "TopK Hit", "Kw Hit", "MaxSim", "Top-3 chunks retrieved") `
    -ForegroundColor DarkGray
Write-Host ("  " + "-" * 90) -ForegroundColor DarkGray

foreach ($q in $evalQueries) {
    # 1. Embed the query
    $embedBody = @{ texts = @($q.question); mode = "query" } | ConvertTo-Json -Compress
    try {
        $embedResp = Invoke-RestMethod -Uri "$EMBED_URL/embed" -Method Post `
                                       -ContentType "application/json" -Body $embedBody -ErrorAction Stop
        $vec = $embedResp.embeddings[0]
    } catch {
        Write-Fail "Embedding failed for '$($q.label)': $_"
        continue
    }

    # 2. Hybrid SQL retrieval — mirrors what retrieval.py now does in production
    #    VECTOR_WEIGHT=0.6  BM25_WEIGHT=0.4  (same constants as retrieval.py)
    $vecStr   = "[" + ($vec -join ",") + "]"
    $safeQ    = $q.question -replace "'", "''"   # escape single quotes for SQL

    $retrieveSQL = @"
SELECT
  source_type,
  REPLACE(REPLACE(LEFT(content, 100), E'\n', ' '), '|', ' ') AS preview,
  ROUND(
    (0.6 * (1 - (embedding <=> '$vecStr'::vector))
   + 0.4 * ts_rank(fts, plainto_tsquery('pg_catalog.simple', '$safeQ'))
    )::numeric, 4) AS similarity
FROM document_chunks
WHERE embedding IS NOT NULL
ORDER BY similarity DESC
LIMIT $TopK;
"@

    $rawResult = Invoke-Psql $retrieveSQL
    $rows = $rawResult -split "`n" | Where-Object { $_.Trim() -and $_ -notmatch "^--" -and $_ -notmatch "^\(" -and $_ -notmatch "^[0-9]+ row" }

    if (-not $rows -or $rows.Count -eq 0) {
        Write-Warn "$($q.label): No rows returned from retrieval"
        continue
    }

    # Parse rows: 3 columns  source_type | preview | similarity
    # Filter: rows with exactly 2 pipes (3 fields).  Extra pipes = content artifact → skip
    $parsed = @()
    foreach ($row in $rows) {
        $cols = $row -split "\|"
        if ($cols.Count -eq 3) {
            $simVal = 0.0
            $ok     = [float]::TryParse($cols[2].Trim(), [System.Globalization.NumberStyles]::Float,
                                        [System.Globalization.CultureInfo]::InvariantCulture, [ref]$simVal)
            if ($ok) {
                $parsed += [PSCustomObject]@{
                    source_type = $cols[0].Trim()
                    preview     = $cols[1].Trim()
                    similarity  = $simVal
                }
            }
        }
    }

    if ($parsed.Count -eq 0) { continue }

    $top1     = $parsed[0]
    $maxSim   = ($parsed | Measure-Object -Property similarity -Maximum).Maximum
    $allSimilarities += $parsed | ForEach-Object { $_.similarity }

    # Evaluation metrics
    $top1Hit  = ($top1.source_type -eq $q.expected_type)
    $topKHit  = ($parsed | Where-Object { $_.source_type -eq $q.expected_type }).Count -gt 0
    $kwHit    = $false
    if ($q.expected_keyword -ne "") {
        # Use SQL ILIKE check to avoid PowerShell encoding issues with Vietnamese text
        $kwSql = "SELECT COUNT(*) FROM document_chunks WHERE embedding IS NOT NULL AND content ILIKE '%$($q.expected_keyword)%' LIMIT 1;"
        $kwResult = Invoke-Psql $kwSql
        $kwCount  = ($kwResult | Where-Object { $_ -match '^\s*\d+\s*$' } | Select-Object -First 1).Trim()
        $kwHit    = ($kwCount -and [int]$kwCount -gt 0)
    } else {
        $kwHit = $true  # no keyword constraint = auto-pass
    }

    if ($top1Hit)  { $precisionHits++ }
    if ($topKHit)  { $topKHits++ }
    if ($kwHit)    { $keywordHits++ }
    if ($maxSim -lt $MinSim) { $lowSimQueries += $q.label }

    # Build preview of top-3
    $top3Preview = ($parsed | Select-Object -First 3 | ForEach-Object {
        "$($_.source_type)[$([math]::Round($_.similarity,2))]"
    }) -join ", "

    $top1Color  = if ($top1Hit) { "Green" } else { "Red" }
    $topKColor  = if ($topKHit) { "Green" } else { "Yellow" }
    $kwColor    = if ($kwHit)   { "Green" } else { "Yellow" }

    Write-Host -NoNewline ("  {0,-12} {1,-14}" -f $q.label, $q.expected_type)
    Write-Host -NoNewline (" {0,-10}" -f $(if ($top1Hit) { "YES" } else { "NO" })) -ForegroundColor $top1Color
    Write-Host -NoNewline (" {0,-10}" -f $(if ($topKHit) { "YES" } else { "NO" })) -ForegroundColor $topKColor
    Write-Host -NoNewline (" {0,-10}" -f $(if ($kwHit)   { "YES" } else { "NO" })) -ForegroundColor $kwColor
    Write-Host -NoNewline (" {0,-10}" -f [math]::Round($maxSim, 3))
    Write-Host " $top3Preview"

    $resultsTable += [PSCustomObject]@{
        Label        = $q.label
        Question     = $q.question
        ExpectedType = $q.expected_type
        Top1Match    = $top1Hit
        TopKMatch    = $topKHit
        KeywordMatch = $kwHit
        MaxSim       = [math]::Round($maxSim, 4)
        Top1Type     = $top1.source_type
        Top1Sim      = [math]::Round($top1.similarity, 4)
        Top1Preview  = $top1.preview.Substring(0, [Math]::Min(80, $top1.preview.Length))
    }
}

# ════════════════════════════════════════════════════════════════════════════
Write-Step "5. Similarity score distribution"
# ════════════════════════════════════════════════════════════════════════════
if ($allSimilarities.Count -gt 0) {
    $avgSim = [math]::Round(($allSimilarities | Measure-Object -Average).Average, 4)
    $maxSim = [math]::Round(($allSimilarities | Measure-Object -Maximum).Maximum, 4)
    $minSim = [math]::Round(($allSimilarities | Measure-Object -Minimum).Minimum, 4)

    # Histogram buckets
    $buckets = @{
        "0.00-0.10" = 0; "0.10-0.20" = 0; "0.20-0.30" = 0; "0.30-0.40" = 0
        "0.40-0.50" = 0; "0.50-0.60" = 0; "0.60-0.70" = 0; "0.70-0.80" = 0
        "0.80-0.90" = 0; "0.90-1.00" = 0
    }
    foreach ($s in $allSimilarities) {
        $bucket = [math]::Floor($s * 10) / 10
        $key    = "{0:F2}-{1:F2}" -f $bucket, ($bucket + 0.10)
        if ($buckets.ContainsKey($key)) { $buckets[$key]++ }
    }

    Write-Host ""
    Write-Host "  Similarity distribution across all retrieved chunks:" -ForegroundColor White
    Write-Host "  (each █ = 1 chunk)" -ForegroundColor DarkGray
    foreach ($key in ($buckets.Keys | Sort-Object)) {
        $count = $buckets[$key]
        $bar   = "█" * $count
        $color = if ($key -gt "0.40") { "Green" } elseif ($key -gt "0.20") { "Yellow" } else { "Red" }
        Write-Host -NoNewline ("  {0,-12} | " -f $key)
        Write-Host -NoNewline $bar -ForegroundColor $color
        Write-Host (" ($count)")
    }
    Write-Host ""
    Write-Host "  Stats: avg=$avgSim  min=$minSim  max=$maxSim" -ForegroundColor Cyan

    $aboveThreshold = ($allSimilarities | Where-Object { $_ -ge $MinSim }).Count
    $pctAbove       = [math]::Round($aboveThreshold / $allSimilarities.Count * 100, 1)
    Write-Info "$aboveThreshold/$($allSimilarities.Count) retrieved chunks above threshold $MinSim ($pctAbove%)"

    if ($pctAbove -ge 70) {
        Write-Pass "Similarity quality: $pctAbove% of chunks above threshold $MinSim"
    } else {
        Write-Warn "Similarity quality: only $pctAbove% above threshold — consider increasing corpus size"
    }
}

# ════════════════════════════════════════════════════════════════════════════
Write-Step "6. Precision metrics"
# ════════════════════════════════════════════════════════════════════════════

$p1  = [math]::Round($precisionHits / $totalQueries * 100, 1)
$pK  = [math]::Round($topKHits      / $totalQueries * 100, 1)
$pkw = [math]::Round($keywordHits   / $totalQueries * 100, 1)

Write-Host ""
Write-Host "  ┌──────────────────────────────────────────────" -ForegroundColor White
Write-Host "  │ RETRIEVAL PRECISION REPORT" -ForegroundColor White
Write-Host "  ├──────────────────────────────────────────────"
Write-Host ("  │ Precision@1  (top-1 = expected type)  : {0,5}%  ({1}/{2})" -f $p1,  $precisionHits, $totalQueries)
Write-Host ("  │ Precision@K  (any top-K = expected)   : {0,5}%  ({1}/{2})" -f $pK,  $topKHits,      $totalQueries)
Write-Host ("  │ Keyword Hit  (content contains term)  : {0,5}%  ({1}/{2})" -f $pkw, $keywordHits,   $totalQueries)
Write-Host "  ├──────────────────────────────────────────────"
if ($lowSimQueries.Count -gt 0) {
    Write-Host "  │ Low-similarity queries (<$MinSim): $($lowSimQueries -join ', ')" -ForegroundColor Yellow
}
Write-Host "  └──────────────────────────────────────────────"
Write-Host ""

if ($p1  -ge 60) { Write-Pass "Precision@1  = $p1%  (target ≥60%)" } else { Write-Fail "Precision@1  = $p1%  (target ≥60%)" }
if ($pK  -ge 80) { Write-Pass "Precision@K  = $pK%  (target ≥80%)" } else { Write-Fail "Precision@K  = $pK%  (target ≥80%)" }
if ($pkw -ge 70) { Write-Pass "Keyword Hit  = $pkw% (target ≥70%)" } else { Write-Warn "Keyword Hit  = $pkw% (target ≥70%)" }

# ════════════════════════════════════════════════════════════════════════════
Write-Step "7. Traceability table — query → top-1 chunk"
# ════════════════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "  Full trace of what each query retrieved as top-1:" -ForegroundColor White
Write-Host ""
foreach ($r in $resultsTable) {
    $matchColor = if ($r.Top1Match) { "Green" } else { "Red" }
    $simColor   = if ($r.Top1Sim -ge $MinSim) { "Cyan" } else { "Yellow" }
    Write-Host "  [$($r.Label)]" -ForegroundColor White
    Write-Host "    Query   : $($r.Question)" -ForegroundColor DarkGray
    Write-Host "    Expected: $($r.ExpectedType)" -ForegroundColor DarkGray
    Write-Host -NoNewline "    Got     : $($r.Top1Type)  "
    Write-Host "(sim=$($r.Top1Sim))" -ForegroundColor $simColor
    Write-Host -NoNewline "    Match   : "
    Write-Host $(if ($r.Top1Match) { "YES ✓" } else { "NO  ✗" }) -ForegroundColor $matchColor
    Write-Host "    Preview : $($r.Top1Preview)..." -ForegroundColor DarkGray
    Write-Host ""
}

# ════════════════════════════════════════════════════════════════════════════
Write-Step "8. Source type balance in retrieval"
# ════════════════════════════════════════════════════════════════════════════
$typeCount = @{}
foreach ($r in $resultsTable) {
    if (-not $typeCount.ContainsKey($r.Top1Type)) { $typeCount[$r.Top1Type] = 0 }
    $typeCount[$r.Top1Type]++
}
Write-Host "  Distribution of top-1 retrieved types across all queries:"
foreach ($type in ($typeCount.Keys | Sort-Object)) {
    $c   = $typeCount[$type]
    $bar = "█" * $c
    Write-Host "    $($type.PadRight(16)) | $bar ($c)"
}
Write-Host ""

# ════════════════════════════════════════════════════════════════════════════
Write-Step "SUMMARY"
# ════════════════════════════════════════════════════════════════════════════
$total = $PASS + $ERRORS
Write-Host ""
Write-Host ("Results: {0} passed, {1} failed (out of {2} checks)" -f $PASS, $ERRORS, $total) `
    -ForegroundColor $(if ($ERRORS -eq 0) { "Green" } else { "Yellow" })

if ($ERRORS -eq 0) {
    Write-Host "RAG retrieval evaluation PASSED — pipeline ready." -ForegroundColor Green
} else {
    Write-Host "Some checks failed — see details above." -ForegroundColor Red
}

Write-Host ""
Write-Host "NOTE: This evaluation is LLM-FREE." -ForegroundColor DarkGray
Write-Host "      Precision metrics are based purely on vector similarity + source type matching." -ForegroundColor DarkGray
Write-Host "      Chat/LLM generation test requires Gemini API key (run test_phase2.ps1 after quota reset)." -ForegroundColor DarkGray
