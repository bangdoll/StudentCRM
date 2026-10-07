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
                img.addEventListener('error', function () {
                    img.classList.add('img-loaded'); // 即使失敗也移除骨架動畫
                }, { once: true });
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

    // ── 5. 自動啟動 ───────────────────────────────────────────
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            initLinkPrefetching();
            initImageEnhancements();
        });
    } else {
        initLinkPrefetching();
        initImageEnhancements();
    }
})();
