#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Phase 3 data seeding script — creates semantically-rich test data for thinh@gmail.com.

.DESCRIPTION
    Creates:
    - 50 transactions (all 8 categories, expense + income, March–April 2026)
    - 15 journal entries (financial + emotional reflection in Vietnamese)
    - 10 mood entries (correlated with financial events)

    All data is optimised for the Phase 2.5/Phase 3 hybrid BM25+vector search.
    Transaction notes are rich Vietnamese so the chunk text (~140 chars) competes
    against journal chunks in retrieval.

.USAGE
    cd backend
    .\scripts\seed_phase3_data.ps1

    Optional flags:
      -BaseUrl "http://localhost:8000"   # override Kong URL
      -Email "other@email.com"           # override account
      -Password "OtherPass@123"
      -WaitSeconds 25                    # embedding pipeline warmup wait
#>

param(
    [string]$BaseUrl    = "http://localhost:8000",
    [string]$Email      = "thinh@gmail.com",
    [string]$Password   = "Thaithinh@123",
    [int]   $WaitSeconds = 25
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Colours ──────────────────────────────────────────────────────────────────
function Write-Step   { param($m) Write-Host "`n==> $m" -ForegroundColor Cyan }
function Write-Ok     { param($m) Write-Host "  [OK] $m" -ForegroundColor Green }
function Write-Warn   { param($m) Write-Host "  [!!] $m" -ForegroundColor Yellow }
function Write-Fail   { param($m) Write-Host "  [XX] $m" -ForegroundColor Red }

# ── API helpers ───────────────────────────────────────────────────────────────
$script:Token = ""

function Invoke-Api {
    param(
        [string]$Method,
        [string]$Path,
        [hashtable]$Body = @{},
        [switch]$Public
    )
    $uri     = "$BaseUrl$Path"
    $headers = @{ "Content-Type" = "application/json" }
    if (-not $Public) {
        $headers["Authorization"] = "Bearer $script:Token"
    }
    try {
        $response = Invoke-RestMethod -Method $Method -Uri $uri `
            -Headers $headers `
            -Body ($Body | ConvertTo-Json -Depth 10 -Compress) `
            -ContentType "application/json"
        return $response
    } catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        $detail     = ""
        try {
            $reader  = [System.IO.StreamReader]::new($_.Exception.Response.GetResponseStream())
            $detail  = $reader.ReadToEnd()
            $reader.Close()
        } catch {}
        Write-Warn "  HTTP $statusCode on $Method $Path — $detail"
        return $null
    }
}

# ── 1. Login ──────────────────────────────────────────────────────────────────
Write-Step "Authenticating as $Email"
$login = Invoke-Api -Method POST -Path "/auth/login" -Public -Body @{
    email    = $Email
    password = $Password
}
if (-not $login -or -not $login.access_token) {
    Write-Fail "Login failed. Is the backend running? Check $BaseUrl"
    exit 1
}
$script:Token = $login.access_token
Write-Ok "JWT obtained (${($script:Token.Length)} chars)"

# ── 2. Transactions ───────────────────────────────────────────────────────────
Write-Step "Creating transactions (50 items)…"

$transactions = @(
    # ── INCOME ──────────────────────────────────────────────────────────────
    @{ type="income"; category="other";         amount=15000000; note="Lương tháng 3/2026 — công ty chi trả đúng hạn, tháng này có thêm phụ cấp xăng 500k";                               transaction_date="2026-03-01" }
    @{ type="income"; category="other";         amount=3500000;  note="Thưởng KPI quý 1 — hoàn thành 115% chỉ tiêu doanh số, nhận thưởng thêm từ phòng kinh doanh";                       transaction_date="2026-03-15" }
    @{ type="income"; category="other";         amount=2000000;  note="Freelance thiết kế UI — làm thêm cuối tuần cho startup thực phẩm hữu cơ, thanh toán qua ngân hàng";               transaction_date="2026-03-22" }
    @{ type="income"; category="other";         amount=15000000; note="Lương tháng 4/2026 — nhận đủ, đã chuyển 3 triệu vào quỹ tiết kiệm khẩn cấp ngay sau khi nhận";                   transaction_date="2026-04-01" }
    @{ type="income"; category="other";         amount=800000;   note="Hoàn tiền bảo hiểm y tế — bệnh viện hoàn lại chi phí khám ngoại trú vượt mức quy định";                          transaction_date="2026-04-10" }

    # ── FOOD ────────────────────────────────────────────────────────────────
    @{ type="expense"; category="food";         amount=45000;    note="Bún bò Huế buổi sáng — hàng quen đầu ngõ, ăn trước khi đi làm";                                                   transaction_date="2026-03-02" }
    @{ type="expense"; category="food";         amount=32000;    note="Cà phê sữa đá take-away — Highlands gần văn phòng, uống mỗi sáng thứ Hai để tỉnh táo họp";                       transaction_date="2026-03-03" }
    @{ type="expense"; category="food";         amount=85000;    note="Cơm văn phòng bữa trưa — set cơm gà và rau luộc, ăn cùng đồng nghiệp ở căng-tin tầng 1";                        transaction_date="2026-03-04" }
    @{ type="expense"; category="food";         amount=220000;   note="Đặt pizza Domino's tối thứ Sáu — date night ở nhà, xem phim Netflix cùng bạn bè";                                transaction_date="2026-03-07" }
    @{ type="expense"; category="food";         amount=150000;   note="Đi ăn lẩu Thái cuối tuần — nhóm 4 người, chia đều mỗi người 150k, vui vẻ và no bụng";                           transaction_date="2026-03-08" }
    @{ type="expense"; category="food";         amount=68000;    note="Phở bò tái đặc biệt — quán phở truyền thống gần nhà, ăn tối hôm tăng ca về muộn";                               transaction_date="2026-03-10" }
    @{ type="expense"; category="food";         amount=380000;   note="Siêu thị VinMart — mua thực phẩm cả tuần: rau củ, thịt, trứng, sữa và đồ ăn sáng cho 3 ngày";                   transaction_date="2026-03-14" }
    @{ type="expense"; category="food";         amount=55000;    note="Bánh mì pate buổi sáng và trà sữa trân châu bữa chiều — bữa nhẹ ngày thứ Tư không muốn ra ngoài";               transaction_date="2026-03-18" }
    @{ type="expense"; category="food";         amount=95000;    note="Cơm niêu thập cẩm bữa tối — trời mưa không muốn nấu, gọi shipper GrabFood giao tận nơi";                        transaction_date="2026-03-24" }
    @{ type="expense"; category="food";         amount=420000;   note="Ăn nhà hàng hải sản sinh nhật bạn — góp tiền ăn tôm hùm và cua rang muối, hơi tốn nhưng vui";                  transaction_date="2026-03-28" }
    @{ type="expense"; category="food";         amount=72000;    note="Bún chả Hà Nội bữa trưa — thử quán mới mở gần công ty, khẩu vị ổn, giá hợp lý";                                transaction_date="2026-04-03" }
    @{ type="expense"; category="food";         amount=310000;   note="Vinmart tuần đầu tháng 4 — bổ sung tủ lạnh sau kỳ nghỉ lễ, mua kho thực phẩm thiết yếu";                        transaction_date="2026-04-05" }

    # ── SHOPPING ────────────────────────────────────────────────────────────
    @{ type="expense"; category="shopping";     amount=450000;   note="Quần jean Levi's sale 30% — mua ở Vincom, size vừa vặn, chất liệu bền, mặc đi làm casual";                      transaction_date="2026-03-05" }
    @{ type="expense"; category="shopping";     amount=890000;   note="Giày sneaker Nike Air Max — giảm giá cuối mùa 40%, cần thay đôi cũ đã mòn đế sau 2 năm dùng";                  transaction_date="2026-03-12" }
    @{ type="expense"; category="shopping";     amount=180000;   note="Sách 'Người giàu có nhất thành Babylon' và 'Nghĩ giàu làm giàu' — đọc để học quản lý tài chính cá nhân";       transaction_date="2026-03-19" }
    @{ type="expense"; category="shopping";     amount=1200000;  note="Tai nghe Bluetooth JBL — mua để dùng online meeting từ xa và nghe nhạc khi tập thể dục";                        transaction_date="2026-03-25" }
    @{ type="expense"; category="shopping";     amount=320000;   note="Son môi và kem dưỡng da Innisfree — mua hàng Hàn Quốc chính hãng ở cửa hàng, chăm sóc bản thân";              transaction_date="2026-04-07" }
    @{ type="expense"; category="shopping";     amount=650000;   note="Áo thun polo và shorts thể thao — chuẩn bị quần áo tập gym mới, cũ đã phai màu và giãn";                      transaction_date="2026-04-12" }

    # ── TRANSPORT ───────────────────────────────────────────────────────────
    @{ type="expense"; category="transport";    amount=230000;   note="Đổ xăng xe máy Honda Wave — đổ full bình ở cây xăng Petrolimex đầu tuần, đủ đi cả tuần";                       transaction_date="2026-03-02" }
    @{ type="expense"; category="transport";    amount=85000;    note="GrabCar đi sân bay — tiễn bạn ra Tân Sơn Nhất lúc 5 giờ sáng, không có xe máy đi được";                       transaction_date="2026-03-09" }
    @{ type="expense"; category="transport";    amount=24000;    note="Vé xe buýt tuyến 01 — đi từ nhà tới trung tâm, tiết kiệm hơn Grab nhưng mất 40 phút";                          transaction_date="2026-03-16" }
    @{ type="expense"; category="transport";    amount=195000;   note="Đổ xăng giữa tháng — giá xăng RON95 tăng nhẹ so với tuần trước, ảnh hưởng chi phí đi lại";                    transaction_date="2026-03-17" }
    @{ type="expense"; category="transport";    amount=62000;    note="GrabBike 3 chuyến trong tuần — trời mưa không đi xe máy được, dùng Grab cho an toàn";                           transaction_date="2026-03-26" }
    @{ type="expense"; category="transport";    amount=220000;   note="Đổ xăng đầu tháng 4 — full bình Honda, đủ đi làm cả 2 tuần nếu không đi chơi xa";                             transaction_date="2026-04-02" }

    # ── HEALTH ──────────────────────────────────────────────────────────────
    @{ type="expense"; category="health";       amount=250000;   note="Khám tổng quát định kỳ — phòng khám đa khoa, xét nghiệm máu và đo huyết áp, mọi chỉ số ổn";                   transaction_date="2026-03-06" }
    @{ type="expense"; category="health";       amount=180000;   note="Thuốc cảm cúm và vitamin — bị cảm nhẹ cuối tuần, mua thuốc hạ sốt, kháng sinh và vitamin C";                  transaction_date="2026-03-11" }
    @{ type="expense"; category="health";       amount=350000;   note="Phí gym tháng 3 — CLB thể dục California Fitness, tập 3 buổi/tuần, đầu tư cho sức khỏe dài hạn";              transaction_date="2026-03-13" }
    @{ type="expense"; category="health";       amount=350000;   note="Phí gym tháng 4 — tiếp tục duy trì thói quen tập luyện, cảm thấy khỏe hơn và ngủ ngon hơn";                  transaction_date="2026-04-04" }

    # ── ENTERTAINMENT ────────────────────────────────────────────────────────
    @{ type="expense"; category="entertainment"; amount=99000;   note="Netflix Premium tháng 3 — chia sẻ với 2 người bạn, xem phim Hàn và documentary về tài chính";                  transaction_date="2026-03-01" }
    @{ type="expense"; category="entertainment"; amount=160000;  note="Xem phim rạp Mega GS — Avatar phần 2 chiếu muộn, ghế VIP, mua thêm bắp rang và nước ngọt";                    transaction_date="2026-03-08" }
    @{ type="expense"; category="entertainment"; amount=120000;  note="Game mobile nạp xu — game nhập vai cùng bạn bè, nạp thêm để mua skin mới trong sự kiện giới hạn";             transaction_date="2026-03-20" }
    @{ type="expense"; category="entertainment"; amount=99000;   note="Netflix Premium tháng 4 — gia hạn thêm 1 tháng, đang xem series tài liệu về tâm lý và tiền bạc";             transaction_date="2026-04-01" }
    @{ type="expense"; category="entertainment"; amount=200000;  note="Pickleball sân trong nhà — đi chơi với 3 đồng nghiệp cuối tuần, hoạt động ngoài trời tốt cho tinh thần";      transaction_date="2026-04-06" }

    # ── EDUCATION ────────────────────────────────────────────────────────────
    @{ type="expense"; category="education";    amount=1500000;  note="Khoá học Python Data Science Udemy — mua lúc sale 95%, học ngoài giờ để nâng cao kỹ năng lập trình";           transaction_date="2026-03-03" }
    @{ type="expense"; category="education";    amount=800000;   note="Giáo trình IELTS Cambridge 18 và luyện nghe — chuẩn bị thi IELTS để du học hoặc xin việc nước ngoài";         transaction_date="2026-03-21" }
    @{ type="expense"; category="education";    amount=2500000;  note="Khoá học quản lý tài chính cá nhân online — 3 tháng học về đầu tư, lập ngân sách và tiết kiệm";              transaction_date="2026-04-09" }

    # ── UTILITIES ────────────────────────────────────────────────────────────
    @{ type="expense"; category="utilities";    amount=680000;   note="Tiền điện tháng 3 — hóa đơn EVN, tháng này dùng điều hòa nhiều do nắng nóng, tăng so với tháng 2";            transaction_date="2026-03-05" }
    @{ type="expense"; category="utilities";    amount=270000;   note="Internet FPT tháng 3 — gia hạn gói 200Mbps, dùng cả cho work-from-home và stream phim";                       transaction_date="2026-03-05" }
    @{ type="expense"; category="utilities";    amount=175000;   note="Cước điện thoại Viettel tháng 3 — gói data 10GB/ngày và gọi nội mạng miễn phí, vừa đủ dùng";                 transaction_date="2026-03-06" }
    @{ type="expense"; category="utilities";    amount=720000;   note="Tiền điện tháng 4 — mùa hè đến sớm, bật điều hòa 24/7, hóa đơn tăng mạnh so với tháng trước";               transaction_date="2026-04-05" }

    # ── OTHER ────────────────────────────────────────────────────────────────
    @{ type="expense"; category="other";        amount=500000;   note="Quà sinh nhật mẹ — mua nước hoa Chanel mini và hộp bánh ngọt, ý nghĩa hơn là tốn kém";                       transaction_date="2026-03-15" }
    @{ type="expense"; category="other";        amount=200000;   note="Đóng góp quỹ lớp cũ — họp mặt cựu sinh viên hàng năm, góp tiền tổ chức và quà tặng thầy cô";               transaction_date="2026-03-27" }
    @{ type="expense"; category="other";        amount=300000;   note="Từ thiện — ủng hộ chiến dịch gây quỹ trẻ em nghèo miền núi qua mạng, nhỏ thôi nhưng vui lòng";              transaction_date="2026-04-08" }
)

$txCreated = 0
$txFailed  = 0
foreach ($tx in $transactions) {
    $result = Invoke-Api -Method POST -Path "/transactions" -Body $tx
    if ($result -and $result.id) {
        $txCreated++
        Write-Ok "$($tx.type) / $($tx.category) / $($tx.transaction_date) — $($tx.amount) VND"
    } else {
        $txFailed++
        Write-Warn "Failed: $($tx.note.Substring(0, [Math]::Min(50, $tx.note.Length)))…"
    }
}
Write-Host "`n  Transactions: $txCreated created, $txFailed failed" -ForegroundColor Cyan

# ── 3. Journal entries ────────────────────────────────────────────────────────
Write-Step "Creating journal entries (15 items)…"

$journals = @(
    @{ content = "Hôm nay nhận lương tháng 3, cảm giác khá nhẹ nhõm. Tháng này mình quyết định lập bảng ngân sách chi tiết hơn sau khi nghe podcast về quản lý tài chính cá nhân. Kế hoạch: 50% cho chi phí thiết yếu (ăn uống, tiện ích, đi lại), 20% tiết kiệm và đầu tư, 30% cho nhu cầu cá nhân và giải trí. Nghe thì đơn giản nhưng thực hiện khó hơn mình tưởng, vì tháng nào cũng có khoản phát sinh ngoài dự kiến. Hôm nay mình đã chuyển ngay 3 triệu vào tài khoản tiết kiệm trước khi tiêu bất cứ thứ gì khác — nguyên tắc 'trả lương cho mình trước'." }
    @{ content = "Cuối tuần đi siêu thị mua đồ ăn cả tuần, chi khoảng 380k. Nhìn hóa đơn mà thấy rõ mình đang tiêu tiền vào những gì. Rau củ: 120k, thịt và cá: 180k, sữa và trứng: 50k, đồ ăn vặt: 30k. Mình tự hỏi: liệu mình có thể nấu ăn ở nhà nhiều hơn và giảm chi phí ăn ngoài xuống không? Tháng trước mình ăn ngoài tổng cộng hết khoảng 1.5 triệu, nếu tự nấu ăn có thể tiết kiệm được 700-800k mỗi tháng. Nhưng vấn đề là thời gian — sau 9 tiếng ở văn phòng, về nhà lúc 7 tối không còn sức nấu. Cần tìm cách cân bằng giữa tiết kiệm và thực tế cuộc sống đi làm." }
    @{ content = "Hôm nay mình mua đôi giày Nike sale 40%, ngốn mất gần 900k. Ban đầu cảm thấy tội lỗi vì 'mua đồ không cần thiết', nhưng nghĩ lại đôi giày cũ đã mòn gần 2 năm rồi. Ranh giới giữa 'nhu cầu thực sự' và 'muốn' khá mơ hồ. Đôi khi mình tự hỏi: nếu không mua vào lúc đang sale thì bao giờ mới mua? Và nếu không mua thì 900k đó sẽ đi đâu — chắc cũng sẽ tiêu vào chỗ khác thôi. Có lẽ điều quan trọng không phải là 'không tiêu tiền' mà là 'tiêu tiền có ý thức và theo kế hoạch'. Tháng tới mình sẽ lập danh sách những thứ cần mua trước khi ra cửa hàng để tránh mua bộc phát." }
    @{ content = "Phát hiện bản thân hay ăn ngoài vào những ngày stress cao độ ở công ty. Hôm nay họp căng thẳng 3 tiếng, xong về lại gọi GrabFood tô cơm niêu 95k thay vì nấu ăn như dự định. Đây là pattern mình nhận ra: cảm xúc tiêu cực → tiêu tiền không có kế hoạch. Bài báo mình đọc gọi đây là 'emotional spending' — tiêu tiền để xoa dịu cảm xúc. Cần tìm những cách khác để giải tỏa stress tốt hơn: đi bộ, nghe nhạc, tâm sự với bạn bè. Không phải lúc nào cũng cần tiêu tiền mới thấy khỏe hơn." }
    @{ content = "Nhìn lại tháng 3, mình tiêu quá tay vào ăn uống và giải trí. Tổng chi ăn uống khoảng 1.8 triệu, giải trí (Netflix, phim, game) khoảng 500k — nhiều hơn kế hoạch 30%. Phần tốt: đã tiết kiệm đúng 3 triệu như kế hoạch, không động vào. Phần cần cải thiện: ăn ngoài quá nhiều lần, đặc biệt là bữa tối. Mục tiêu tháng 4: giới hạn ăn ngoài tối không quá 5 lần/tháng và tự nấu ăn ít nhất 4 buổi tối/tuần. Xem có thực hiện được không. Việc ghi chép chi tiêu giúp mình nhìn rõ thói quen hơn rất nhiều — trước đây không biết tiền đi đâu hết." }
    @{ content = "Hôm nay thưởng KPI dưới dự kiến một chút, không được 5 triệu như năm ngoái mà chỉ 3.5 triệu. Ban đầu hơi thất vọng nhưng sau nghĩ lại thì đây vẫn là một khoản thêm ngoài lương rất đáng trân trọng. Mình quyết định dùng 1.5 triệu để mua khoá học Python Data Science đang muốn học từ lâu, còn lại 2 triệu bổ sung vào quỹ tiết kiệm. Đầu tư vào kỹ năng của bản thân là kiểu đầu tư sinh lời tốt nhất trong dài hạn — ít nhất đó là điều mình tin. Nếu học xong và apply được Data Science vào công việc, cơ hội tăng lương sẽ cao hơn." }
    @{ content = "Đọc xong cuốn 'Người giàu có nhất thành Babylon' tuần này. Mấy nguyên tắc cơ bản mà sao mình chưa bao giờ áp dụng: (1) Để lại ít nhất 1/10 thu nhập cho bản thân mình, (2) Kiểm soát chi tiêu, (3) Làm tiền sinh ra tiền. Principle đơn giản nhưng để thực hành cần kỷ luật thật sự. Mình đang ở bước (1) và (2), chưa nghĩ tới (3). Có lẽ bước tiếp theo là tìm hiểu về đầu tư cơ bản: để tiền trong bank thì lãi suất không đủ bù lạm phát. Cần học thêm về quỹ ETF và đầu tư định kỳ." }
    @{ content = "Tháng này tiền điện hơn 680k, tăng khá nhiều so với tháng 2 (khoảng 480k). Nguyên nhân chính là bật điều hòa nhiều hơn vì nắng nóng bất thường. Mình thử tính: nếu nâng nhiệt độ điều hòa từ 24°C lên 26°C và chỉ bật khi ngủ thay vì cả ngày, có thể tiết kiệm được 30-40% hóa đơn điện. Thử nghiệm tháng 4 xem sao. Chi phí tiện ích (điện + internet + điện thoại) đang chiếm khoảng 7-8% thu nhập — ngưỡng lý tưởng là dưới 10% nên tạm chấp nhận được." }
    @{ content = "Hôm nay khám sức khỏe định kỳ, tốn 250k nhưng tất cả chỉ số đều ổn: cholesterol, đường huyết, huyết áp đều trong ngưỡng bình thường. Cảm thấy nhẹ nhõm vì sức khỏe là tài sản lớn nhất — bệnh tật mới là thứ tốn tiền nhiều nhất. Bác sĩ nhắc nên tập thể dục đều đặn và ăn uống lành mạnh hơn. Phí gym 350k/tháng mình đang trả thực ra không đắt nếu tính ra lợi ích lâu dài. Cần tận dụng hết thẻ gym thay vì chỉ đi 2 buổi/tuần. Mục tiêu: tăng lên 4 buổi/tuần trong tháng 4." }
    @{ content = "Ngồi tính toán để lập kế hoạch tài chính cho 6 tháng tới. Thu nhập trung bình 15-16 triệu/tháng (bao gồm lương + thu nhập phụ). Chi phí cố định: ăn uống 1.5tr, tiện ích 1.1tr, đi lại 0.5tr, gym 0.35tr, Netflix 0.1tr → tổng ~3.55 triệu. Tiết kiệm mục tiêu 3 triệu/tháng. Còn lại ~8-9 triệu cho chi phí biến đổi và cá nhân. Nghe có vẻ thoải mái nhưng mình hay 'rò rỉ' ở đây — mua sắm bốc đồng, ăn nhà hàng đắt, đặt đồ ăn khuya. Cần có 'ngân sách vui vẻ' cụ thể thay vì để mở thì dễ vượt hơn." }
    @{ content = "Freelance project đầu tiên hoàn thành, nhận 2 triệu đồng cho 3 ngày thiết kế UI. Cảm giác rất khác khi kiếm được tiền từ kỹ năng của mình ngoài lương công ty. Nhận ra rằng: thời gian rảnh cuối tuần có giá trị kinh tế thực sự. Nếu làm freelance 2 project/tháng thì có thêm khoảng 3-4 triệu, bằng 20-25% thu nhập hiện tại. Nhưng phải cân nhắc với việc nghỉ ngơi và sức khỏe tinh thần. Tháng tới sẽ thử nhận thêm 1 project nữa xem có ổn không. Thu nhập đa dạng giúp mình tự tin hơn về tài chính." }
    @{ content = "Cuối tuần cùng nhóm bạn ăn hải sản mừng sinh nhật, tốn 420k. Có khoảnh khắc ngần ngại vì nghĩ 'tháng này chi ăn uống đã nhiều rồi', nhưng rồi tự nhủ: những kỷ niệm với bạn bè quan trọng hơn 420k. Tài chính lành mạnh không có nghĩa là không bao giờ tận hưởng cuộc sống. Quan trọng là phải cân bằng: có ngân sách rõ ràng, thực hiện được mục tiêu tiết kiệm, nhưng vẫn cho phép mình trải nghiệm và tận hưởng. Tiết kiệm để sống tốt hơn, không phải để khắc khổ." }
    @{ content = "Tháng 4 bắt đầu với tâm thế khá tốt. Tổng kết tháng 3: tiết kiệm được 3 triệu (đúng kế hoạch), tổng chi khoảng 11.5 triệu. Điểm vượt kế hoạch: ăn uống (+300k), mua sắm (+200k). Điểm tốt: không chi tiêu bất cứ thứ gì quá hạn mức 2 triệu mà không suy nghĩ trước. Tháng 4 mình muốn thử thêm 1 thách thức: 'No-spend Sunday' — mỗi Chủ nhật không chi tiêu gì ngoài thiết yếu. Nếu làm được 4 Chủ nhật, mình sẽ tiết kiệm thêm ~500-700k. Nhỏ nhưng là bài tập kỷ luật tốt." }
    @{ content = "Hôm nay đăng ký khoá học quản lý tài chính cá nhân online 3 tháng, 2.5 triệu. Khoản này lớn nhất tháng 4 nhưng mình rất kỳ vọng. Nội dung bao gồm: lập ngân sách theo phương pháp envelope budgeting, đầu tư cơ bản cho người mới bắt đầu, quỹ khẩn cấp và bảo hiểm, kế hoạch nghỉ hưu sớm. Nếu học và áp dụng được ít nhất 20% nội dung, khoản 2.5 triệu sẽ sinh lời rất nhiều về tài chính. Quyết định tốt hay không sẽ thấy sau 6 tháng khi nhìn lại số dư." }
    @{ content = "Nhận hoàn tiền bảo hiểm 800k hôm nay, đúng lúc cần. Trước đây mình hay thấy tiền bảo hiểm y tế bị trừ vào lương là 'mất đi', nhưng lần này được hoàn lại thì thấy rõ giá trị thực của nó. Quyết định chuyển toàn bộ 800k này vào quỹ khẩn cấp — hiện quỹ này đang có khoảng 8.5 triệu, mục tiêu là đạt 30 triệu (tương đương 2 tháng chi phí sinh hoạt đầy đủ). Còn xa mục tiêu nhưng đang đi đúng hướng. Quỹ khẩn cấp cho mình cảm giác an toàn tâm lý rất lớn — biết rằng nếu có chuyện bất ngờ xảy ra vẫn có chỗ đứng vững." }
)

$jCreated = 0
$jFailed  = 0
foreach ($j in $journals) {
    $result = Invoke-Api -Method POST -Path "/journal/entries" -Body $j
    if ($result -and $result.id) {
        $jCreated++
        $preview = $j.content.Substring(0, [Math]::Min(60, $j.content.Length))
        Write-Ok "$preview…"
    } else {
        $jFailed++
        Write-Warn "Failed journal entry"
    }
}
Write-Host "`n  Journal entries: $jCreated created, $jFailed failed" -ForegroundColor Cyan

# ── 4. Mood entries ───────────────────────────────────────────────────────────
Write-Step "Creating mood entries (10 items)…"

$moods = @(
    @{ score=4; note="Nhận lương và chuyển tiết kiệm ngay — cảm giác chủ động kiểm soát tài chính, tự tin hơn về tương lai" }
    @{ score=2; note="Họp căng thẳng xong lại đặt đồ ăn sinh ra chi phí không cần thiết, thất vọng về sự thiếu kỷ luật của bản thân" }
    @{ score=5; note="Hoàn thành project freelance đầu tiên và nhận thanh toán — cảm giác tự lập và có thêm nguồn thu nhập rất phấn khích" }
    @{ score=3; note="Ngày bình thường, chi tiêu trong kế hoạch, không có gì đặc biệt vui hay buồn, ổn định là tốt" }
    @{ score=4; note="Khám sức khỏe kết quả tốt và biết rằng mình đang đầu tư đúng vào bản thân, cả sức khỏe lẫn kiến thức" }
    @{ score=2; note="Nhìn lại hóa đơn tháng 3 thấy vượt kế hoạch ăn uống và mua sắm — tự trách vì thiếu kỷ luật, nhưng không nên quá khắt khe" }
    @{ score=5; note="Ăn sinh nhật bạn vui vẻ — nhắc nhở bản thân rằng tiền bạc phục vụ cuộc sống, không phải ngược lại" }
    @{ score=4; note="Bắt đầu tháng 4 với kế hoạch rõ ràng hơn, cảm thấy thêm kiểm soát và hướng đi, tinh thần tích cực" }
    @{ score=3; note="Đăng ký khoá học tài chính — hơi lo về khoản tiền lớn nhưng tin đây là đầu tư xứng đáng cho tương lai" }
    @{ score=4; note="Quỹ khẩn cấp đang tăng dần, cảm giác an toàn tài chính ngày càng rõ nét — tinh thần ổn định và thanh thản" }
)

$mCreated = 0
$mFailed  = 0
foreach ($m in $moods) {
    $result = Invoke-Api -Method POST -Path "/journal/moods" -Body $m
    if ($result -and $result.id) {
        $mCreated++
        Write-Ok "Score $($m.score)/5 — $($m.note.Substring(0, [Math]::Min(55, $m.note.Length)))…"
    } else {
        $mFailed++
        Write-Warn "Failed mood entry"
    }
}
Write-Host "`n  Mood entries: $mCreated created, $mFailed failed" -ForegroundColor Cyan

# ── 5. Wait for embedding pipeline ────────────────────────────────────────────
Write-Step "Waiting ${WaitSeconds}s for RabbitMQ → insight-service embedding pipeline…"
$elapsed = 0
while ($elapsed -lt $WaitSeconds) {
    $pct = [int](($elapsed / $WaitSeconds) * 50)
    $bar = ("#" * $pct).PadRight(50)
    Write-Host -NoNewline "`r  [$bar] ${elapsed}s / ${WaitSeconds}s"
    Start-Sleep -Seconds 1
    $elapsed++
}
Write-Host "`r  [$("=" * 50)] ${WaitSeconds}s done   "

# ── 6. Summary ────────────────────────────────────────────────────────────────
Write-Step "Seeding complete!"
Write-Host @"

  Account   : $Email
  Transactions : $txCreated created  ($txFailed failed)
  Journal entries : $jCreated created  ($jFailed failed)
  Mood entries    : $mCreated created  ($mFailed failed)

  Chunks should now appear in insight_db.document_chunks.
  Sample RAG queries to test:
    - "Tháng 3 tôi chi tiêu vào ăn uống bao nhiêu?"
    - "Những lần tôi chi tiêu nhiều nhất là gì?"
    - "Tôi có xu hướng tiêu tiền khi stress không?"
    - "Thu nhập của tôi tháng 3 là bao nhiêu?"
    - "Tình trạng sức khỏe tài chính của tôi như thế nào?"
    - "Tôi đã tiết kiệm được bao nhiêu?"
    - "Chi tiêu giải trí của tôi có hợp lý không?"

"@ -ForegroundColor Green
