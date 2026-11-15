"""打包版主程序入口：不带参数 → 图形界面；带参数 → 命令行（测试用，如 --file x.wav --no-ui --fast）"""
import sys

if __name__ == "__main__":
    if len(sys.argv) > 1:
        from livecaption.main import main
        main(sys.argv[1:])
    else:
        from livecaption.ui.app import main
        main()
