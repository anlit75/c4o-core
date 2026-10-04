# --- From here down this file is c4o-core's stub.mk. Do not edit it. ---
#
# The commands -- make all, make gds, make report and the rest -- are in the
# c4o-core image named above, in /opt/c4o-core/rules.mk, so a fix to them
# arrives with the image. `make help` lists them. Targets of your own go below
# the include; docs/makefile.md in c4o-core says what they may use.
#
# Inside the image (the Dev Container) the rules are a local file. On a host
# they are copied out of the image into .c4o/, once for each image: the file is
# named after the image's id, so the rules are always the ones of the image
# that runs, and a `docker pull` that brings a newer image brings its rules.
#
# C4O_RULES=<file> uses that file and no Docker at all.
ifndef C4O_RULES
ifneq ($(wildcard /opt/c4o-core/rules.mk),)
C4O_RULES := /opt/c4o-core/rules.mk
else
C4O_IMAGE_ID := $(shell docker image inspect -f '{{.Id}}' $(C4O_IMAGE) 2>/dev/null)
ifeq ($(C4O_IMAGE_ID),)
$(info Pulling $(C4O_IMAGE) ...)
C4O_IMAGE_ID := $(shell docker pull -q $(C4O_IMAGE) >/dev/null 2>&1; docker image inspect -f '{{.Id}}' $(C4O_IMAGE) 2>/dev/null)
endif
ifeq ($(C4O_IMAGE_ID),)
$(error Cannot get $(C4O_IMAGE). The commands of this Makefile come out of that image, so it needs Docker running and the image name to be right. Check 'docker info' and 'docker pull $(C4O_IMAGE)')
endif
C4O_RULES := .c4o/$(subst sha256:,,$(C4O_IMAGE_ID)).mk
$(C4O_RULES):
	@mkdir -p .c4o
	@rm -f .c4o/*.mk .c4o/*.tmp
	@docker run --rm --entrypoint cat $(C4O_IMAGE) /opt/c4o-core/rules.mk > $@.tmp \
		|| { rm -f $@.tmp; echo "❌ [ERROR] $(C4O_IMAGE) has no /opt/c4o-core/rules.mk. This Makefile needs c4o-core 2.17 or newer."; exit 1; }
	@mv $@.tmp $@
endif
endif
include $(C4O_RULES)
