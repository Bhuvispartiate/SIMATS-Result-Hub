document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('login-form');
    const submitBtn = document.getElementById('submit-btn');
    const btnText = submitBtn.querySelector('.btn-text');
    const loader = submitBtn.querySelector('.loader');

    const loginView = document.getElementById('login-view-container');
    const dashboardView = document.getElementById('dashboard-view');
    const errorMessage = document.getElementById('error-message');
    const errorText = document.getElementById('error-text');
    const logoutBtn = document.getElementById('logout-btn');

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const username = document.getElementById('username').value.trim();
        const password = document.getElementById('password').value;

        if (!username || !password) return;

        setLoading(true);
        errorMessage.classList.add('hidden');

        try {
            const formData = new FormData();
            formData.append('username', username);
            formData.append('password', password);

            const response = await fetch('/api/login', {
                method: 'POST',
                body: formData
            });

            const data = await response.json().catch(() => ({}));

            if (!response.ok) {
                throw new Error(data.detail || `Server error: ${response.status}`);
            }

            if (data.success && data['ASP.NET_SessionId']) {
                // Hide login, show dashboard
                loginView.classList.add('hidden');
                dashboardView.classList.remove('hidden');

                // Start fetch marks process
                fetchMarks(username, data['ASP.NET_SessionId']);
            } else {
                throw new Error("Login succeeded but no session cookie was returned.");
            }
        } catch (error) {
            console.error("Login error:", error);
            errorText.textContent = error.message || "Failed to login. Please try again.";
            errorMessage.classList.remove('hidden');

            // Trigger shake animation again by cloning and replacing
            const newError = errorMessage.cloneNode(true);
            errorMessage.parentNode.replaceChild(newError, errorMessage);
        } finally {
            setLoading(false);
        }
    });

    logoutBtn.addEventListener('click', () => {
        dashboardView.classList.add('hidden');
        loginView.classList.remove('hidden');
        form.reset();
        document.getElementById('username').focus();
    });

    async function fetchMarks(username, sessionId) {
        const loading = document.getElementById('dashboard-loading');
        const container = document.getElementById('cards-container');
        const errorMsg = document.getElementById('dashboard-error');
        const userDisplay = document.getElementById('user-display');

        const circle = document.querySelector('.progress-ring__circle');
        const percentageText = document.getElementById('progress-percentage');
        const progressStatus = document.getElementById('progress-text');

        const radius = circle.r.baseVal.value;
        const circumference = radius * 2 * Math.PI;

        circle.style.strokeDasharray = `${circumference} ${circumference}`;
        circle.style.strokeDashoffset = circumference;

        userDisplay.textContent = `${username}`;

        loading.classList.remove('hidden');
        container.classList.add('hidden');
        errorMsg.classList.add('hidden');

        function setProgress(percent) {
            const offset = circumference - percent / 100 * circumference;
            circle.style.strokeDashoffset = offset;
            percentageText.textContent = Math.round(percent);
        }

        setProgress(0);
        progressStatus.textContent = 'Connecting to SIMATS...';

        let progress = 0;
        const progressInterval = setInterval(() => {
            progress += Math.random() * 12;
            if (progress > 90) progress = 90;
            setProgress(progress);

            if (progress > 30 && progress < 60) {
                progressStatus.textContent = 'Fetching course enrollments...';
            } else if (progress >= 60) {
                progressStatus.textContent = 'Aggregating detailed mark splits...';
            }
        }, 400);

        try {
            const formData = new FormData();
            formData.append('username', username);
            formData.append('session_id', sessionId);

            const response = await fetch('/api/fetch-marks', {
                method: 'POST',
                body: formData
            });

            const data = await response.json().catch(() => ({}));

            clearInterval(progressInterval);

            if (!response.ok) throw new Error(data.detail || 'Failed to fetch marks');

            setProgress(100);
            progressStatus.textContent = 'Data loaded successfully!';

            setTimeout(() => {
                loading.classList.add('hidden');
                renderCards(data.data);
                container.classList.remove('hidden');
            }, 800);

        } catch (e) {
            clearInterval(progressInterval);
            loading.classList.add('hidden');
            errorMsg.textContent = e.message;
            errorMsg.classList.remove('hidden');

            // Render basic fallback if UI needs resetting
            container.innerHTML = '';
        }
    }

    function renderCards(data) {
        const container = document.getElementById('cards-container');
        container.innerHTML = '';

        if (!data || data.length === 0) {
            container.innerHTML = '<div style="color:var(--text-muted); text-align:center; width: 100%; grid-column: 1 / -1; padding: 40px;">No course enrollments found for this period.</div>';
            return;
        }

        data.forEach((item, index) => {
            const card = document.createElement('div');
            card.className = 'course-card';
            card.style.opacity = '0';

            // Staggered animation
            card.animate([
                { opacity: 0, transform: 'translateY(30px) scale(0.95)' },
                { opacity: 1, transform: 'translateY(0) scale(1)' }
            ], {
                duration: 500,
                easing: 'cubic-bezier(0.175, 0.885, 0.32, 1.275)',
                fill: 'forwards',
                delay: index * 100 // Stagger delay
            });

            const c = item.course;
            const marks = item.marks;
            const error = item.error;

            let marksHtml = '';
            let totalObtained = 0;
            if (error) {
                marksHtml = `<div class="card-error">${error}</div>`;
            } else if (marks && marks.length > 0) {
                const targetCategories = [
                    "Class Test (IA)",
                    "Research",
                    "Class Practical",
                    "University Theory",
                    "University Practical"
                ];

                marks.forEach(m => {
                    const category = m.RubricCategory ? m.RubricCategory.trim() : "";
                    if (targetCategories.includes(category)) {
                        const val = parseFloat(m.OrginalConvertedMark);
                        if (!isNaN(val)) {
                            totalObtained += val;
                        }
                    }
                });
                totalObtained = Math.round(totalObtained * 100) / 100;

                const list = marks.map(m => {
                    const isPass = m.IsPassed;
                    const statusClass = isPass ? 'mark-pass' : 'mark-fail';
                    const statusText = isPass ? 'PASS' : 'FAIL';
                    return `
                        <li class="mark-item">
                            <div class="mark-info">
                                <span class="mark-name">${m.RubricCategory}</span>
                                <span class="mark-type">${m.Type}</span>
                            </div>
                            <div class="mark-score-container">
                                <span class="mark-value">${m.OrginalConvertedMark} <span style="opacity:0.4;font-size:12px;">/ ${m.RubricsMaxMark}</span></span>
                                <div><span class="mark-status ${statusClass}">${statusText}</span></div>
                            </div>
                        </li>
                    `;
                }).join('');
                marksHtml = `<ul class="mark-list">${list}</ul>`;
            } else {
                marksHtml = `<div style="padding:40px 20px; color:var(--text-muted); text-align:center;">No marks available for this course</div>`;
            }

            card.innerHTML = `
                <div class="card-header">
                    <span class="course-code">${c.CourseCode || '-'}</span>
                    <h3>${c.CourseName || 'Unknown Course'}</h3>
                    <div class="card-meta">
                        <span class="month-badge">${c.MonthYearValue || '-'}</span>
                        <div style="display: flex; gap: 8px; align-items: center;">
                            ${marks && !error ? `<span class="grade-badge" style="background: rgba(138,43,226,0.15); border-color: rgba(138,43,226,0.3); color: #fff;">Total: ${totalObtained}/500</span>` : ''}
                            <span class="grade-badge">Grade: ${c.FinalGrade || 'N/A'}</span>
                        </div>
                    </div>
                </div>
                <div class="card-body">
                    ${marksHtml}
                </div>
            `;

            container.appendChild(card);
        });
    }

    function setLoading(isLoading) {
        submitBtn.disabled = isLoading;
        if (isLoading) {
            btnText.classList.add('hidden');
            loader.classList.remove('hidden');
        } else {
            btnText.classList.remove('hidden');
            loader.classList.add('hidden');
        }
    }
});
