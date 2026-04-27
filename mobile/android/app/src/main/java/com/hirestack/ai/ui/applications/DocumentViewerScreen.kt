package com.hirestack.ai.ui.applications

import android.annotation.SuppressLint
import android.webkit.WebSettings
import android.webkit.WebView
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import com.hirestack.ai.ui.components.BrandBackground
import com.hirestack.ai.ui.components.BrandTopBar
import com.hirestack.ai.ui.components.confirm
import kotlinx.coroutines.launch
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ContentCopy
import androidx.compose.material.icons.outlined.Share

/**
 * Lightweight HTML document preview rendered with a sandboxed WebView.
 * Wraps the document in a styled shell that matches the brand palette and
 * uses a serif-ish typographic stack so the rendered CV feels print-quality.
 *
 * Security: JS disabled, file access disabled, no external content allowed
 * via baseUrl=null (the HTML the backend returns is sanitized server-side).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DocumentViewerScreen(
    title: String,
    html: String,
    onClose: () -> Unit,
) {
    val clipboard = androidx.compose.ui.platform.LocalClipboardManager.current
    val snackbar = com.hirestack.ai.ui.components.LocalSnackbar.current
    val scope = com.hirestack.ai.ui.components.LocalAppScope.current
    val haptic = androidx.compose.ui.platform.LocalHapticFeedback.current
    Scaffold(
        topBar = {
            BrandTopBar(
                title = title,
                onBack = onClose,
                actions = {
                    val shareCtx = androidx.compose.ui.platform.LocalContext.current
                    androidx.compose.material3.IconButton(onClick = {
                        val plain = androidx.core.text.HtmlCompat.fromHtml(html, androidx.core.text.HtmlCompat.FROM_HTML_MODE_COMPACT).toString().trim()
                        val send = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                            type = "text/plain"
                            putExtra(android.content.Intent.EXTRA_SUBJECT, title)
                            putExtra(android.content.Intent.EXTRA_TEXT, plain)
                        }
                        runCatching { shareCtx.startActivity(android.content.Intent.createChooser(send, title)) }
                    }) {
                        androidx.compose.material3.Icon(
                            androidx.compose.material.icons.Icons.Outlined.Share,
                            contentDescription = "Share document",
                        )
                    }
                    androidx.compose.material3.IconButton(onClick = {
                        val plain = androidx.core.text.HtmlCompat.fromHtml(html, androidx.core.text.HtmlCompat.FROM_HTML_MODE_COMPACT).toString().trim()
                        clipboard.setText(androidx.compose.ui.text.AnnotatedString(plain))
                        haptic.confirm()
                        scope.launch { snackbar.showSnackbar("Document copied") }
                    }) {
                        androidx.compose.material3.Icon(
                            androidx.compose.material.icons.Icons.Outlined.ContentCopy,
                            contentDescription = "Copy document text",
                        )
                    }
                },
            )
        },
        containerColor = Color.Transparent,
    ) { padding ->
        BrandBackground {
            Box(
                Modifier
                    .fillMaxSize()
                    .padding(padding),
            ) {
                HtmlView(html = html)
            }
        }
    }
}

@SuppressLint("SetJavaScriptEnabled")
@Composable
private fun HtmlView(html: String) {
    val ctx = LocalContext.current
    val wrapped = remember(html) { wrap(html) }
    AndroidView(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        factory = {
            WebView(ctx).apply {
                settings.apply {
                    javaScriptEnabled = false
                    allowFileAccess = false
                    allowContentAccess = false
                    @Suppress("DEPRECATION")
                    allowFileAccessFromFileURLs = false
                    @Suppress("DEPRECATION")
                    allowUniversalAccessFromFileURLs = false
                    cacheMode = WebSettings.LOAD_NO_CACHE
                    builtInZoomControls = true
                    displayZoomControls = false
                }
                setBackgroundColor(android.graphics.Color.TRANSPARENT)
            }
        },
        update = { wv ->
            wv.loadDataWithBaseURL(null, wrapped, "text/html", "utf-8", null)
        },
    )
}

private val SHELL_CSS = """
<style>
  :root {
    color-scheme: dark;
  }
  html, body {
    margin: 0; padding: 0;
    background: transparent;
    color: #F5F5FB;
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, sans-serif;
    line-height: 1.5;
    font-size: 16px;
  }
  .doc {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 18px;
    padding: 22px;
  }
  h1 { font-size: 22px; font-weight: 700; margin: 0 0 12px; color: #FFFFFF; }
  h2 { font-size: 18px; font-weight: 600; margin: 18px 0 8px; color: #C4B5FD; }
  h3 { font-size: 16px; font-weight: 600; margin: 14px 0 6px; color: #93C5FD; }
  p, li { font-size: 15px; }
  ul { padding-left: 18px; }
  a { color: #67E8F9; text-decoration: none; }
  hr { border: 0; border-top: 1px solid rgba(255,255,255,0.10); margin: 14px 0; }
  table { width: 100%; border-collapse: collapse; }
  td, th { padding: 6px 8px; border-bottom: 1px solid rgba(255,255,255,0.08); text-align: left; }
</style>
""".trimIndent()

private fun wrap(html: String): String =
    """
    <!doctype html>
    <html><head><meta name="viewport" content="width=device-width, initial-scale=1"/>$SHELL_CSS</head>
    <body><div class="doc">$html</div></body></html>
    """.trimIndent()
