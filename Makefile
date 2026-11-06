PY ?= python3
ZIP ?= ../jobs-pipeline.zip

.PHONY: test run accuracy evidence zip clean

## Offline unit + integration tests (fake LLM client, network blocked)
test:
	$(PY) -I -B tests/run.py

## Classify s.csv with rules only -> out/
run:
	$(PY) -m jobs_pipeline run --input s.csv --out out

## Score the hand-labeled sample (fill out/label_sample.csv human_family first)
accuracy:
	$(PY) -m jobs_pipeline accuracy --labels out/label_sample.csv --key out/label_sample_key.csv

## Regenerate runtime + test evidence in docs/evidence/
evidence:
	mkdir -p docs/evidence
	{ echo "# make evidence: $$(date -u +%Y-%m-%dT%H:%M:%SZ) on $$(uname -sm)"; $(PY) --version; \
	  $(PY) -c "import subprocess,sys,time; t=time.perf_counter(); \
	r=subprocess.run([sys.executable,'-m','jobs_pipeline','run','--input','s.csv','--out','out']); \
	print(f'wall_clock_seconds (whole process, incl. interpreter start): {time.perf_counter()-t:.3f}'); \
	sys.exit(r.returncode)"; } > docs/evidence/run_log.txt 2>&1
	cp out/run_stats.json docs/evidence/run_stats.json
	$(PY) -I -B tests/run.py > docs/evidence/test_output.txt 2>&1

## Zip the project to $(ZIP). Excludes caches and SPEC-FROM-GAP-PLAN.txt (unrelated
## planning notes that name third parties).
zip:
	rm -f $(ZIP)
	$(PY) -c "import os,zipfile,sys; z=zipfile.ZipFile(sys.argv[1],'w',zipfile.ZIP_DEFLATED); \
	[z.write(os.path.join(d,f), os.path.join('jobs-pipeline', os.path.relpath(os.path.join(d,f),'.'))) \
	 for d,ds,fs in os.walk('.') if '__pycache__' not in d for f in fs if f != 'SPEC-FROM-GAP-PLAN.txt']; z.close()" $(ZIP)
	@echo "wrote $(ZIP)"

clean:
	rm -rf out __pycache__ */__pycache__
