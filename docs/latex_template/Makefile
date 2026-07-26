# Makefile for SJTUThesis

# Basename of thesis
THESIS = main
OUTPUT_DIR = ../latex_output
OUTPUT_PDF = $(OUTPUT_DIR)/$(THESIS).pdf

# Option for latexmk
LATEXMK_OPT = -time -file-line-error -halt-on-error -interaction=nonstopmode -outdir=$(OUTPUT_DIR)
LATEXMK_OPT_PVC = $(LATEXMK_OPT) -pvc

# make deletion work on Windows
ifdef SystemRoot
	RM = del /Q
	OPEN = start
else
	RM = rm -f
	OPEN = open
endif

.PHONY : all pvc view wordcount clean cleanall FORCE_MAKE

all : $(OUTPUT_PDF)

$(OUTPUT_DIR) :
	@mkdir -p $@

$(OUTPUT_PDF) : $(THESIS).tex FORCE_MAKE | $(OUTPUT_DIR)
	@latexmk $(LATEXMK_OPT) $<

pvc : $(THESIS).tex | $(OUTPUT_DIR)
	@latexmk $(LATEXMK_OPT_PVC) $(THESIS)

view : $(OUTPUT_PDF)
	$(OPEN) $<

wordcount : $(THESIS).tex
	@if grep -v ^% $< | grep -q '\\documentclass\[[^\[]*lang\s*=\s*en'; then \
		texcount $< -inc -char-only | awk '/total/ {getline; print "英文字符数\t\t\t:",$$4}'; \
	else \
		texcount $< -inc -ch-only   | awk '/total/ {getline; print "纯中文字数\t\t\t:",$$4}'; \
	fi
	@texcount $< -inc -chinese | awk '/total/ {getline; print "总字数（英文单词 + 中文字）\t:",$$4}'

clean :
	-@latexmk -c -silent -outdir=$(OUTPUT_DIR) $(THESIS).tex 2> /dev/null

cleanall :
	-@latexmk -C -silent -outdir=$(OUTPUT_DIR) $(THESIS).tex 2> /dev/null
