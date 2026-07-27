### Overleaf

If you are an [Overleaf](https://www.overleaf.com?r=sdkbtJ4qGS8kDZQQ&rm=d&rs=b) user, you can create your own project through the link below.

[![Overleaf](https://img.shields.io/badge/Overleaf-SJTUThesis-green.svg)](https://www.overleaf.com/latex/templates/sjtuthesis-latex-thesis-template-for-shanghai-jiao-tong-university/mkdwbyjbtfgg?r=sdkbtJ4qGS8kDZQQ&rm=d&rs=b) 

## Usage

### Linux & macOS Users

It is recommended to use GNU make utility with `Makefile` provided in the template.

```bash
make all                      # compile and generate main.pdf
make clean                    # remove useless files
make cleanall                 # remove everything produced by make all
make wordcount                # count the words of the thesis
```

### Windows Users

We also provided a batch script `Compile.bat` for Windows users. You can double-click the batch file to compile instantly, or use it in Command Prompt to access extra features.

```bash
.\Compile.bat thesis          # compile and generate main.pdf
.\Compile.bat clean           # remove useless files
.\Compile.bat cleanall        # remove everything produced by make all
.\Compile.bat wordcount       # count the words of the thesis
