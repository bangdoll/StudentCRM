/**
 * instant-prefetch.js - StudentCRM 全站極速秒開與圖片骨架屏引擎
 * 核心能力：
 * 1. 0ms 觸摸/懸停即時預載（Instant Prefetch）
 * 2. 圖片波浪微光骨架屏（Skeleton Shimmer & Fade-in）
 * 3. 節流防抖與省流量（Save-Data）感知
 */

(function () {
    'use strict';

    // ── 1. 狀態與常數 ──────────────────────────────────────────
    const prefetchedUrls = new Set();
    const isSaveData = Boolean(
        navigator.connection && (navigator.connection.saveData || /(2g|slow-2g)/i.test(navigator.connection.effectiveType))
    );

    // ── 2. 預載核心邏輯 ────────────────────────────────────────
    function prefetchUrl(url) {
        if (!url || isSaveData) return;

        try {
            const parsed = new URL(url, window.location.origin);
            // 僅預載同源、非檔案下載、非登出或外部連結
            if (parsed.origin !== window.location.origin) return;
            // Personal and computed documents load only after navigation.
            if (/^\/(search|my|hub|digital-management)(\/|$)/.test(parsed.pathname)) return;
            if (parsed.pathname === window.location.pathname && parsed.search === window.location.search) return;
            if (parsed.pathname.startsWith('/logout') || parsed.pathname.startsWith('/api/')) return;
            if (parsed.pathname.match(/\.(pdf|zip|mp4|png|jpg|jpeg|gif)$/i)) return;

            const targetKey = parsed.pathname + parsed.search;
            if (prefetchedUrls.has(targetKey)) return;
            prefetchedUrls.add(targetKey);

            // 優先使用 <link rel="prefetch">，次選 fetch(..., { priority: 'low' })
            if (document.createElement('link').relList && document.createElement('link').relList.supports('prefetch')) {
                const link = document.createElement('link');
                link.rel = 'prefetch';
                link.href = targetKey;
                link.as = 'document';
                document.head.appendChild(link);
            } else {
                fetch(targetKey, { credentials: 'same-origin', priority: 'low' }).catch(function () {});
            }
        } catch (e) {
            // 靜默略過不合規的 URL
        }
    }

    // ── 3. 全局點擊/懸停/觸摸監聽器 ───────────────────────────
    function initLinkPrefetching() {
        function handleInteraction(e) {
            const anchor = e.target.closest('a');
            if (!anchor) return;
            const href = anchor.getAttribute('href');
            if (href && !href.startsWith('#') && !href.startsWith('javascript:')) {
                prefetchUrl(href);
            }
        }

        // 行動裝置一碰即載（touchstart），桌面滑鼠一移即載（mouseenter）
        document.addEventListener('touchstart', handleInteraction, { passive: true });
        document.addEventListener('mouseover', handleInteraction, { passive: true });
    }

    // ── 4. 圖片骨架屏與平滑漸顯控制器 ─────────────────────────
    function initImageEnhancements() {
        function setupImage(img) {
            if (img.dataset.enhanced) return;
            img.dataset.enhanced = 'true';

            // 加上原生現代屬性
            if (!img.getAttribute('loading')) img.setAttribute('loading', 'lazy');
            if (!img.getAttribute('decoding')) img.setAttribute('decoding', 'async');
            img.classList.add('img-lazy-fade');

            // 包裹或標記骨架容器
            const parent = img.parentElement;
            if (parent && !parent.classList.contains('img-skeleton-wrapper')) {
                img.classList.add('img-has-shimmer');
            }

            if (img.complete && img.naturalWidth > 0) {
                img.classList.add('img-loaded');
            } else {
                img.addEventListener('load', function () {
                    img.classList.add('img-loaded');
                }, { once: true });
                
                // 圖片載入失敗自癒重試與優雅降級
                img.addEventListener('error', function () {
                    var retryCount = parseInt(img.dataset.retryCount || '0', 10);
                    if (retryCount < 2) {
                        // 首次或二次失敗：可能 Vercel 正在部署中，延遲重試
                        img.dataset.retryCount = (retryCount + 1).toString();
                        setTimeout(function () {
                            var originalSrc = img.dataset.originalSrc || img.src;
                            img.dataset.originalSrc = originalSrc;
                            var separator = originalSrc.indexOf('?') === -1 ? '?' : '&';
                            img.src = originalSrc.split('?_retry=')[0] + separator + '_retry=' + Date.now();
                        }, 2500);
                    } else {
                        // 重試多次仍未就緒：啟動優雅降級卡片，隱藏破碎圖標
                        img.classList.add('img-loaded');
                        img.style.display = 'none';
                        if (!img.nextElementSibling || !img.nextElementSibling.classList.contains('img-fallback-card')) {
                            var fallback = document.createElement('div');
                            fallback.className = 'img-fallback-card';
                            fallback.innerHTML = '<span class="img-fallback-icon">☁️</span>' +
                                '<div class="img-fallback-info">' +
                                    '<div class="img-fallback-title">雲端圖片同步中</div>' +
                                    '<div class="img-fallback-desc">圖片素材正在同步至 CDN 節點，請稍候刷新</div>' +
                                '</div>' +
                                '<button type="button" class="img-fallback-btn">🔄 點擊重試</button>';
                            fallback.querySelector('.img-fallback-btn').addEventListener('click', function (e) {
                                e.preventDefault();
                                fallback.remove();
                                img.style.display = '';
                                img.dataset.retryCount = '0';
                                var sep = img.src.indexOf('?') === -1 ? '?' : '&';
                                img.src = img.src.split('?_retry=')[0] + sep + '_retry=' + Date.now();
                            });
                            img.parentNode.insertBefore(fallback, img.nextSibling);
                        }
                    }
                });
            }
        }

        // 處理現有圖片
        document.querySelectorAll('img').forEach(setupImage);

        // 監聽動態插入的圖片（如 Markdown 或非同步載入）
        if (window.MutationObserver) {
            const observer = new MutationObserver(function (mutations) {
                mutations.forEach(function (m) {
                    m.addedNodes.forEach(function (node) {
                        if (node.nodeType === 1) {
                            if (node.tagName === 'IMG') {
                                setupImage(node);
                            } else {
                                node.querySelectorAll && node.querySelectorAll('img').forEach(setupImage);
                            }
                        }
                    });
                });
            });
            observer.observe(document.body, { childList: true, subtree: true });
        }
    }

    // ── 5. 即時無刷換頁引擎 (Instant SPA Navigation / Turbo-like PJAX) ──
    let progressBar = null;
    let progressTimer = null;
    let isNavigating = false;

    function getProgressBar() {
        if (!progressBar) {
            progressBar = document.getElementById('instant-progress-bar');
            if (!progressBar) {
                progressBar = document.createElement('div');
                progressBar.id = 'instant-progress-bar';
                document.body.appendChild(progressBar);
            }
        }
        return progressBar;
    }

    function startProgress() {
        const bar = getProgressBar();
        clearTimeout(progressTimer);
        bar.className = 'active';
        bar.style.width = '25%';
        progressTimer = setTimeout(function () {
            bar.style.width = '75%';
        }, 150);
    }

    function finishProgress() {
        const bar = getProgressBar();
        clearTimeout(progressTimer);
        bar.style.width = '100%';
        bar.className = 'done';
        setTimeout(function () {
            bar.className = '';
            bar.style.width = '0%';
        }, 350);
    }

    async function navigateTo(url, pushState) {
        if (isNavigating) return;
        isNavigating = true;
        startProgress();
        try {
            const resp = await fetch(url, {
                headers: { 'X-Requested-With': 'StudentCRM-Instant' },
                credentials: 'same-origin'
            });

            if (!resp.ok) {
                window.location.href = url;
                return;
            }

            const html = await resp.text();
            const parser = new DOMParser();
            const newDoc = parser.parseFromString(html, 'text/html');

            document.title = newDoc.title;

            // 平滑替換 body 內容
            const newBody = newDoc.body;
            document.body.innerHTML = newBody.innerHTML;
            document.body.className = newBody.className;
            document.body.classList.add('instant-fade-enter');

            // 重新執行新頁面中的 inline scripts
            const scripts = document.body.querySelectorAll('script');
            scripts.forEach(function (oldScript) {
                if (oldScript.src && oldScript.src.includes('instant-prefetch.js')) return;
                const newScript = document.createElement('script');
                Array.from(oldScript.attributes).forEach(function (attr) {
                    newScript.setAttribute(attr.name, attr.value);
                });
                newScript.appendChild(document.createTextNode(oldScript.innerHTML));
                oldScript.parentNode.replaceChild(newScript, oldScript);
            });

            if (pushState !== false) {
                window.history.pushState({ instant: true, url: url }, newDoc.title, url);
            }

            window.scrollTo({ top: 0, behavior: 'instant' });
            finishProgress();
            isNavigating = false;

            // 重新初始化各元件
            initLinkPrefetching();
            initImageEnhancements();
            document.dispatchEvent(new Event('DOMContentLoaded'));
        } catch (err) {
            isNavigating = false;
            window.location.href = url;
        }
    }

    function initInstantNavigation() {
        document.addEventListener('click', function (e) {
            if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) {
                return;
            }

            const anchor = e.target.closest('a');
            if (!anchor) return;

            const href = anchor.getAttribute('href');
            if (!href || href.startsWith('#') || href.startsWith('javascript:')) return;
            if (anchor.target && anchor.target !== '_self') return;
            if (anchor.hasAttribute('download') || anchor.hasAttribute('data-no-pjax')) return;

            try {
                const parsed = new URL(href, window.location.origin);
                if (parsed.origin !== window.location.origin) return;
                if (parsed.pathname === window.location.pathname && parsed.search === window.location.search) return;
                if (parsed.pathname.startsWith('/logout') || parsed.pathname.startsWith('/api/') || parsed.pathname.startsWith('/trigger_open')) return;
                if (parsed.pathname.match(/\.(pdf|zip|mp4|png|jpg|jpeg|gif|svg)$/i)) return;

                e.preventDefault();
                navigateTo(parsed.href, true);
            } catch (err) {
                // 忽略解析錯誤，交由原生導航處理
            }
        });

        window.addEventListener('popstate', function () {
            navigateTo(window.location.href, false);
        });
    }

    // ── 6. 自動啟動 ───────────────────────────────────────────
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            initLinkPrefetching();
            initImageEnhancements();
            initInstantNavigation();
        });
    } else {
        initLinkPrefetching();
        initImageEnhancements();
        initInstantNavigation();
    }
})();
