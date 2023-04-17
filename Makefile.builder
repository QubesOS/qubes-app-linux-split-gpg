ifeq ($(PACKAGE_SET),dom0)
	RPM_SPEC_FILES := rpm_spec/gpg-split-dom0.spec
else ifeq ($(PACKAGE_SET),vm)
ifneq ($(filter $(DISTRIBUTION), debian qubuntu),)
	DEBIAN_BUILD_DIRS := debian
endif
	RPM_SPEC_FILES := rpm_spec/gpg-split.spec
	ARCH_BUILD_DIRS := archlinux

# Support for new packaging
ifneq ($(filter $(DISTRIBUTION), archlinux),)
	VERSION := $(file <$(ORIG_SRC)/$(DIST_SRC)/version)
	GIT_TARBALL_NAME ?= qubes-gpg-split-$(VERSION)-1.tar.gz
	SOURCE_COPY_IN := source-archlinux-copy-in

source-archlinux-copy-in: PKGBUILD = $(CHROOT_DIR)/$(DIST_SRC)/$(ARCH_BUILD_DIRS)/PKGBUILD
source-archlinux-copy-in:
	cp $(PKGBUILD).in $(CHROOT_DIR)/$(DIST_SRC)/PKGBUILD
	sed -i "s/@VERSION@/$(VERSION)/g" $(CHROOT_DIR)/$(DIST_SRC)/PKGBUILD
	sed -i "s/@REL@/1/g" $(CHROOT_DIR)/$(DIST_SRC)/PKGBUILD
endif

endif
