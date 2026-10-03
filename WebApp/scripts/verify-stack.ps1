param([string]$BaseUrl = 'http://127.0.0.1:8080/api', [switch]$WithExam)
. "$PSScriptRoot/api-common.ps1"
try {
    Wait-TaskBackend
    $taskAdmin = Get-TaskAdminToken
    $taskInfra = Invoke-TaskApi GET '/admin/infrastructure' -Token $taskAdmin
    foreach ($taskName in @('PostgreSQL','Redis','MinIO')) {
        Assert-Task ($taskInfra.$taskName -eq 'UP') "$taskName chưa khả dụng."
    }
    Write-Output 'PASS: PostgreSQL, Redis, MinIO.'
    # Creates test accounts and retains their practice/exam history; never changes the content bank.
    $taskSuffix = [Guid]::NewGuid().ToString('N')
    $taskPassword = [Guid]::NewGuid().ToString('N')
    $taskUser = Invoke-TaskApi POST '/auth/register' @{name='Kiểm thử tích hợp';email="check-$taskSuffix@example.test";password=$taskPassword}
    Assert-Task ($taskUser.user.role -eq 'USER') 'Đăng ký phải chỉ tạo USER.'
    $taskDenied = $false
    try { $null = Invoke-TaskApi GET '/admin/users' -Token $taskUser.accessToken } catch { if ($_.Exception.Message -match '^HTTP 403') { $taskDenied=$true } else { throw } }
    Assert-Task $taskDenied 'USER đọc được API quản trị.'
    foreach ($taskKind in @('questions','signs','documents','penalties')) {
        $null = Invoke-TaskApi GET "/$taskKind" -Token $taskUser.accessToken
    }
    Write-Output 'PASS: tự đăng ký USER, phân quyền và API nội dung.'
    if ($WithExam) {
        $taskOther = Invoke-TaskApi POST '/auth/register' @{name='Kiểm thử sở hữu';email="other-$taskSuffix@example.test";password=$taskPassword}
        $taskBank = @(Invoke-TaskApi GET '/admin/questions' -Token $taskAdmin)
        $taskAnswers = @{}
        foreach ($taskQuestion in $taskBank) { $taskAnswers[$taskQuestion.id] = $taskQuestion.data.correctAnswer }
        $taskExam = Invoke-TaskApi POST '/exams' -Token $taskUser.accessToken
        Assert-Task ($taskExam.questions.Count -eq 30) 'Đề phải đủ 30 câu.'
        $taskDenied = $false
        try { $null = Invoke-TaskApi GET "/exams/$($taskExam.id)" -Token $taskOther.accessToken } catch { if ($_.Exception.Message -match '^HTTP 404') { $taskDenied=$true } else { throw } }
        Assert-Task $taskDenied 'Tài khoản khác đọc được bài thi.'
        foreach ($taskQuestion in $taskExam.questions) {
            Assert-Task (!($taskQuestion.PSObject.Properties.Name -contains 'correctAnswer')) 'Lộ đáp án khi đang thi.'
            Assert-Task (!($taskQuestion.PSObject.Properties.Name -contains 'critical')) 'Lộ cờ điểm liệt khi đang thi.'
            Assert-Task ($taskAnswers.ContainsKey($taskQuestion.questionId)) 'Không tìm thấy đáp án quản trị.'
            $null = Invoke-TaskApi PUT "/exams/$($taskExam.id)/answers/$($taskQuestion.questionId)" @{selected=[int]$taskAnswers[$taskQuestion.questionId]} $taskUser.accessToken
            if ($taskQuestion.imageKey) {
                # Check protected snapshot media through the same HTTP client.
                $taskRequest = [Net.Http.HttpRequestMessage]::new([Net.Http.HttpMethod]::Get, "$BaseUrl/exams/$($taskExam.id)/questions/$($taskQuestion.questionId)/media")
                $taskRequest.Headers.Authorization = [Net.Http.Headers.AuthenticationHeaderValue]::new('Bearer',$taskUser.accessToken)
                try {
                    $taskResponse = $taskHttp.SendAsync($taskRequest).GetAwaiter().GetResult()
                    try { Assert-Task $taskResponse.IsSuccessStatusCode 'Không tải được ảnh bài thi từ MinIO.' } finally { $taskResponse.Dispose() }
                } finally { $taskRequest.Dispose() }
            }
        }
        $taskResult = Invoke-TaskApi POST "/exams/$($taskExam.id)/submit" -Token $taskUser.accessToken
        Assert-Task ($taskResult.score -eq 30 -and $taskResult.passed) 'Chấm đúng tất cả phải đạt 30/30.'
        $taskRepeat = Invoke-TaskApi POST "/exams/$($taskExam.id)/submit" -Token $taskUser.accessToken
        Assert-Task ($taskRepeat.score -eq 30 -and $taskRepeat.submittedAt -eq $taskResult.submittedAt) 'Nộp lại thay đổi kết quả.'
        $taskQuestion = $taskExam.questions[0]
        $taskStudy = Invoke-TaskApi POST "/study/$($taskQuestion.questionId)/answer" @{selected=[int]$taskAnswers[$taskQuestion.questionId]} $taskUser.accessToken
        Assert-Task $taskStudy.correct 'Ôn tập chấm sai đáp án.'
        $taskProgress = @(Invoke-TaskApi GET '/progress' -Token $taskUser.accessToken)
        Assert-Task (($taskProgress | Measure-Object -Property practiced -Sum).Sum -ge 1) 'Không lưu tiến độ ôn tập.'
        Write-Output 'PASS: đề B, quyền sở hữu, ẩn đáp án, ảnh MinIO, chấm/nộp lại và tiến độ.'
    } else { Write-Output 'SKIP: thi/ôn tập; sau khi duyệt ngân hàng, chạy lại với -WithExam.' }
    $null = Invoke-TaskApi POST '/auth/logout' -Token $taskUser.accessToken
    $taskRevoked = $false
    try { $null = Invoke-TaskApi GET '/auth/me' -Token $taskUser.accessToken } catch { if ($_.Exception.Message -match '^HTTP 401') { $taskRevoked=$true } else { throw } }
    Assert-Task $taskRevoked 'JWT chưa thu hồi sau đăng xuất.'
    Write-Output 'PASS: thu hồi JWT. KAG chưa thuộc đợt kiểm tra này.'
} finally { $taskHttp.Dispose() }
