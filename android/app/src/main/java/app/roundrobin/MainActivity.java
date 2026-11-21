package app.roundrobin;

import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.database.Cursor;
import android.graphics.Bitmap;
import android.graphics.ImageDecoder;
import android.provider.OpenableColumns;
import android.webkit.MimeTypeMap;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Base64;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import androidx.activity.ComponentActivity;
import androidx.activity.OnBackPressedCallback;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.PickVisualMediaRequest;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.core.content.FileProvider;
import androidx.webkit.WebViewAssetLoader;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Round Robin for Android: shows the app (assets/index.html) in Android's built-in WebView,
 * served from a stable https address so its saved data (IndexedDB) persists.
 * Adds what a bare WebView lacks: the photo picker, saving files, copying text, and the back button.
 */
public class MainActivity extends ComponentActivity {
    private static final String HOME = "https://appassets.androidplatform.net/assets/index.html";

    private WebView web;
    private ValueCallback<Uri[]> pendingChooser;
    private ActivityResultLauncher<PickVisualMediaRequest> pickImages;
    private ActivityResultLauncher<String[]> openDocument;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        pickImages = registerForActivityResult(
                new ActivityResultContracts.PickMultipleVisualMedia(),
                (List<Uri> uris) -> deliverCopies(uris));
        openDocument = registerForActivityResult(
                new ActivityResultContracts.OpenDocument(),
                (Uri uri) -> deliverCopies(uri == null ? null : Collections.singletonList(uri)));

        final WebViewAssetLoader assets = new WebViewAssetLoader.Builder()
                .addPathHandler("/assets/", new WebViewAssetLoader.AssetsPathHandler(this))
                .build();

        // Debug builds only: lets automated tests drive the page from outside.
        if ((getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0) {
            WebView.setWebContentsDebuggingEnabled(true);
        }

        web = new WebView(this);
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(true);
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        s.setTextZoom(100);

        web.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                return assets.shouldInterceptRequest(request.getUrl());
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri u = request.getUrl();
                if ("appassets.androidplatform.net".equals(u.getHost())) return false;
                try { startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (Exception ignored) { }
                return true;
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (pendingChooser != null) pendingChooser.onReceiveValue(null);
                pendingChooser = callback;
                boolean wantsImages = false;
                for (String t : params.getAcceptTypes()) {
                    if (t != null && t.startsWith("image")) wantsImages = true;
                }
                try {
                    if (wantsImages) {
                        pickImages.launch(new PickVisualMediaRequest.Builder()
                                .setMediaType(ActivityResultContracts.PickVisualMedia.ImageOnly.INSTANCE)
                                .build());
                    } else {
                        openDocument.launch(new String[]{"*/*"});
                    }
                    return true;
                } catch (Exception e) {
                    pendingChooser = null;
                    return false;
                }
            }
        });

        web.addJavascriptInterface(new Bridge(), "RRAndroid");

        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                web.evaluateJavascript("window.__rrBack ? window.__rrBack() : false", result -> {
                    if (!"true".equals(result)) {
                        setEnabled(false);
                        getOnBackPressedDispatcher().onBackPressed();
                        setEnabled(true);
                    }
                });
            }
        });

        if (savedInstanceState != null) web.restoreState(savedInstanceState);
        else web.loadUrl(HOME);
    }

    /**
     * Copies picked files into the app's own storage and hands the page those copies.
     * The photo picker strips location data on the fly, so a photo's real size can differ from the size
     * it reports, and the WebView then refuses to read it ("NotReadableError"). Copies are always consistent.
     * HEIC/HEIF photos are converted to JPG on the way, since the WebView can't display them.
     */
    private void deliverCopies(List<Uri> picked) {
        if (picked == null || picked.isEmpty()) { deliver(null); return; }
        new Thread(() -> {
            File dir = new File(getCacheDir(), "picked");
            deleteTree(dir);
            List<Uri> copies = new ArrayList<>();
            for (int i = 0; i < picked.size(); i++) {
                try { copies.add(copyIn(picked.get(i), new File(dir, String.valueOf(i)))); }
                catch (Exception ignored) { /* the page reports how many files it couldn't read */ }
            }
            Uri[] result = copies.isEmpty() ? null : copies.toArray(new Uri[0]);
            runOnUiThread(() -> deliver(result));
        }).start();
    }

    private Uri copyIn(Uri src, File folder) throws Exception {
        ContentResolver cr = getContentResolver();
        String mime = cr.getType(src);
        String name = displayName(src);
        if (name == null || name.isEmpty()) name = "file";
        if (!name.contains(".") && mime != null) {
            String ext = MimeTypeMap.getSingleton().getExtensionFromMimeType(mime);
            if (ext != null) name = name + "." + ext;
        }
        folder.mkdirs();
        boolean heic = (mime != null && (mime.contains("heic") || mime.contains("heif")))
                || name.toLowerCase().matches(".*\\.hei[cf]$");
        File dest;
        if (heic) {
            dest = new File(folder, name.replaceAll("\\.[^.]*$", "") + ".jpg");
            Bitmap bmp = ImageDecoder.decodeBitmap(ImageDecoder.createSource(cr, src));
            try (OutputStream os = new FileOutputStream(dest)) { bmp.compress(Bitmap.CompressFormat.JPEG, 90, os); }
            bmp.recycle();
        } else {
            dest = new File(folder, name);
            try (InputStream in = cr.openInputStream(src); OutputStream os = new FileOutputStream(dest)) {
                if (in == null) throw new Exception("no data");
                byte[] buf = new byte[64 * 1024];
                int n;
                while ((n = in.read(buf)) > 0) os.write(buf, 0, n);
            }
        }
        return FileProvider.getUriForFile(this, getPackageName() + ".files", dest);
    }

    private String displayName(Uri uri) {
        try (Cursor c = getContentResolver().query(uri, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (c != null && c.moveToFirst()) return c.getString(0);
        } catch (Exception ignored) { }
        String last = uri.getLastPathSegment();
        return last == null ? null : last.replaceAll("[/\\\\]", "_");
    }

    private static void deleteTree(File f) {
        File[] kids = f.listFiles();
        if (kids != null) for (File k : kids) deleteTree(k);
        f.delete();
    }

    private void deliver(Uri[] uris) {
        if (pendingChooser != null) {
            pendingChooser.onReceiveValue(uris);
            pendingChooser = null;
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        web.saveState(outState);
    }

    @Override
    protected void onDestroy() {
        if (web != null) web.destroy();
        super.onDestroy();
    }

    /** Called from the page as window.RRAndroid. */
    private class Bridge {
        /** Saves a file. Images go to Pictures/Round Robin (shows in the gallery); anything else to Download/Round Robin.
         *  Returns the folder it saved to, or "" if it failed. */
        @JavascriptInterface
        public String saveFile(String name, String mime, String base64) {
            try {
                byte[] data = Base64.decode(base64, Base64.DEFAULT);
                boolean image = mime != null && mime.startsWith("image/");
                String folder = (image ? Environment.DIRECTORY_PICTURES : Environment.DIRECTORY_DOWNLOADS) + "/Round Robin";
                Uri collection = image
                        ? MediaStore.Images.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
                        : MediaStore.Downloads.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY);
                ContentValues cv = new ContentValues();
                cv.put(MediaStore.MediaColumns.DISPLAY_NAME, name);
                cv.put(MediaStore.MediaColumns.MIME_TYPE, mime == null ? "application/octet-stream" : mime);
                cv.put(MediaStore.MediaColumns.RELATIVE_PATH, folder);
                cv.put(MediaStore.MediaColumns.IS_PENDING, 1);
                ContentResolver cr = getContentResolver();
                Uri uri = cr.insert(collection, cv);
                if (uri == null) return "";
                try (OutputStream os = cr.openOutputStream(uri)) {
                    if (os == null) return "";
                    os.write(data);
                }
                cv.clear();
                cv.put(MediaStore.MediaColumns.IS_PENDING, 0);
                cr.update(uri, cv, null, null);
                return folder;
            } catch (Exception e) {
                return "";
            }
        }

        @JavascriptInterface
        public boolean copyText(String text) {
            try {
                ClipboardManager cm = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
                cm.setPrimaryClip(ClipData.newPlainText("Round Robin ranking", text));
                return true;
            } catch (Exception e) {
                return false;
            }
        }
    }
}
