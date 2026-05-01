compile:P4C_IMAGE = p4lang/p4c
P4_FILE = p4/leaf/leaf.p4
JSON_OUT = build/leaf.json
P4INFO_OUT = build/leaf.p4info.txt

compile:
	docker run --rm -it \
		-v "$$(pwd)":/workspace \
		-w /workspace \
		$(P4C_IMAGE) \
		p4c-bm2-ss $(P4_FILE) \
			--p4runtime-files $(P4INFO_OUT) \
			--p4runtime-format text \
			-o $(JSON_OUT)

shell:
	docker run --rm -it \
		-v "$$(pwd)":/workspace \
		-w /workspace \
		$(P4C_IMAGE) \
		bash