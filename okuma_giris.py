"""okuma_giris.py — paketlenmiş sürümün (OkumaAtolyesi.exe) tek giriş noktası.

Exe'de python.exe yoktur; kaynaktan çalışırken ayrı betik olarak başlatılan
parçalar burada exe'nin kendisine yönlendirilir:

    OkumaAtolyesi.exe                       okuyucu (kitaplık)
    OkumaAtolyesi.exe belge.docx            belge editörü
    OkumaAtolyesi.exe kitap.pdf             okuyucu; PDF kitaplığa eklenip açılır
    OkumaAtolyesi.exe --data-dir <klasör>   okuyucu, verilen kütüphaneyle (MCP open_reader)
    OkumaAtolyesi.exe --render-worker       sayfa çizim süreci (core.RenderProcess)
    OkumaAtolyesi.exe --mcp [--data-dir ..] stdio MCP sunucusu (server.py)
    OkumaAtolyesi.exe --kayit-kaldir        "Birlikte aç" kaydını siler (kaldırıcı)

Kaynaktan çalışırken bu dosya kullanılmaz (ac.pyw, app.py, server.py).
"""
import sys


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--render-worker":
        import render_worker
        return render_worker.main()
    if arg == "--kayit-kaldir":
        # Kaldırıcı çağırır: "Birlikte aç" kaydı (HKCU) iz bırakmasın.
        from belge import kayit
        try:
            kayit.kaldir()
        except OSError:
            pass
        return 0
    if arg == "--mcp":
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        import server
        server.main()
        return 0
    yol = next((a for a in sys.argv[1:] if not a.startswith("-")), "")
    if yol.lower().endswith(".docx"):
        from belge.editor import main as editor
        return editor([sys.argv[0], yol])
    import app
    return app.main() or 0


if __name__ == "__main__":
    sys.exit(main())
