### Overleaf

[![Overleaf](https://img.shields.io/badge/Overleaf-SJTUThesis-green.svg)](https://www.overleaf.com/latex/templates/sjtuthesis-latex-thesis-template-for-shanghai-jiao-tong-university/mkdwbyjbtfgg?r=sdkbtJ4qGS8kDZQQ&rm=d&rs=b)

点击 [链接](https://www.overleaf.com/latex/templates/sjtuthesis-latex-thesis-template-for-shanghai-jiao-tong-university/mkdwbyjbtfgg?r=sdkbtJ4qGS8kDZQQ&rm=d&rs=b) 即可直接使用。

如果需要在其他在线 LaTeX 平台上使用（比如 [latex.sjtu.edu.cn](https://latex.sjtu.edu.cn)），您可以下载 [最新版压缩包](https://github.com/sjtug/SJTUThesis/archive/refs/heads/master.zip)，然后上传至相应平台。请注意，Overleaf 默认使用 pdflatex 编译，您需要设置使用 XeLaTeX 编译器。

## 模板使用

如果你不熟悉 LaTeX 的编译流程，请**不要**直接使用编译器进行编译。针对不同的平台，模版提供了相应的编译脚本。在编译前，需要安装最新的 TeXLive 发行版。

### VSCode 用户

安装 “LaTeX Workshop” 后，选择 `Recipe: latexmk (xelatex)` 编译即可，并在设置中将 `latex-workshop.latex.recipe.default` 改为 `lastUsed` 以一直使用该选项编译。

### TeXStudio 用户

在TexStudio的菜单栏中，Options-Configure TeXstudio界面中，修改以下两处：

Commands-Latexmk一项修改为`latexmk -silent -synctex=1 -xelatex %`

Build-Default Compiler一项修改为`txs:///latexmk`

<details>

<summary>展开配置</summary>

<img src="https://user-images.githubusercontent.com/84025388/142163308-3d31f905-af78-40cb-bff1-851cdab04c87.png" width=500px/>

<img src="https://user-images.githubusercontent.com/84025388/142163346-63ec7b7e-932f-44c5-90c4-3b35e435545d.png" width=500px/>

</details>

### Linux 与 macOS 用户

推荐使用模版提供的 `Makefile` 进行编译，具体来说我们提供了如下几条可用的命令：

```bash
make all                      # 编译生成 main.pdf
make clean                    # 删除编译所产生的中间文件
make cleanall                 # 删除 main.pdf 和所有中间文件
make wordcount                # 论文字数统计
```

### Windows 用户

对于 Windows 用户，我们也提供了编译脚本 `Compile.bat`。可以双击直接编译，也可以在命令提示符窗口中使用脚本提供的额外功能：

```bash
.\Compile.bat thesis          # 编译生成 main.pdf
.\Compile.bat clean           # 删除编译所产生的中间文件
.\Compile.bat cleanall        # 删除 main.pdf 和所有中间文件
.\Compile.bat wordcount       # 论文字数统计
```
