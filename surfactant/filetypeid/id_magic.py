# Copyright 2023 Lawrence Livermore National Security, LLC
# See the top-level LICENSE file for details.
#
# SPDX-License-Identifier: MIT
import json
import os
import pathlib
import tarfile
from enum import Enum, auto
from typing import Optional

import surfactant.plugin
from surfactant.infoextractors.coff_file import COFF_MAGIC_TARGET_NAME


class ExeType(Enum):
    ELF = auto()
    PE = auto()
    OLE = auto()
    JAVA_MACHOFAT = auto()
    MACHO32 = auto()
    MACHO64 = auto()


def is_docker_archive(filepath: str) -> bool:
    try:
        # pylint: disable=too-many-return-statements
        with tarfile.open(filepath) as tar:
            try:
                manifest_info = tar.getmember("manifest.json")
                if not manifest_info.isfile():
                    return False
                with tar.extractfile(manifest_info) as manifest_file:
                    manifest = json.load(manifest_file)
                    # There's one entry in the list for each image
                    if not isinstance(manifest, list):
                        return False
                    for data in manifest:
                        # Just check if this data member exists
                        _ = tar.getmember(data["Config"])
                        # Now check that each of the layers exist
                        for layer in data["Layers"]:
                            _ = tar.getmember(layer)
                    # Everything seems to exist and be in order; this is most likely a Docker archive
                    return True
            except KeyError:
                return False
    except tarfile.ReadError:
        return False


@surfactant.plugin.hookimpl(tryfirst=True)
def identify_file_type(filepath: str) -> Optional[str]:
    # pylint: disable=too-many-return-statements
    try:
        with open(filepath, "rb") as f:
            magic_bytes = f.read(265)
            if magic_bytes[:4] == b"\x7fELF":
                return "ELF"
            if magic_bytes[:2] == b"MZ":
                # Several file types start with the same `MZ` signature, so we need to handle them.
                # Regardless, the initial header (may) contain a pointer to an additional COFF
                # header, so we look for that as the first step.
                coff_addr = (
                    int.from_bytes(magic_bytes[0x3C:0x40], byteorder="little", signed=False)
                    & 0xFFFF
                )

                # Check to see if the coff_addr is still within the initial read; if not, we read up
                # to where it is.
                if coff_addr > len(magic_bytes):
                    magic_bytes += f.read(coff_addr + 4 - len(magic_bytes))

                # If coff_addr is still longer than what has been read so far, it points off the end
                # of the file, so the file is either malformed or something else is up.
                if coff_addr + 4 > len(magic_bytes):
                    return "Malformed PE"

                if magic_bytes[coff_addr : coff_addr + 4] != b"PE\x00\x00":
                    return "DOS"

                # Check for the linux kernel header at 0x202 (may require a second read)
                if len(magic_bytes) < 0x206:
                    magic_bytes += f.read(265)

                if magic_bytes[0x202:0x206] == b"HdrS":
                    return "Linux Kernel Image"

                # Otherwise, call it a PE and be done with it.
                return "PE"

            if magic_bytes[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
                # MSI (install), MSP (patch), MST (transform), and MSM (merge) files are all types of OLE files
                # the root storage object CLSID is used to identify what it is (+ file extension)
                return "OLE"
            # Microsoft CAB files
            if magic_bytes[:4] == b"MSCF":
                return "MSCAB"
            # InstallShield CAB files
            if magic_bytes[:4] == b"ISc(":
                return "ISCAB"
            # For gzipped data, also filter by extension to avoid huge number of entries with limited info
            if magic_bytes[:2] == b"\x1f\x8b":
                if is_docker_archive(filepath):
                    return "DOCKER_GZIP"
                return "GZIP"
            # Check for compressed TAR files (tar.bz2, tar.xz)
            if magic_bytes[:3] == b"BZh":
                return "BZIP2"
            if magic_bytes[:6] == b"\xfd\x37\x7a\x58\x5a\x00":
                return "XZ"
            if magic_bytes[257:265] == b"ustar\x0000" or magic_bytes[257:265] == b"ustar  \x00":
                if is_docker_archive(filepath):
                    return "DOCKER_TAR"
                return "TAR"
            if magic_bytes[:6] == b"\x52\x61\x72\x21\x1a\x07":
                return "RAR"
            if magic_bytes[:4] in [b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"]:
                suffix = pathlib.Path(filepath).suffix.lower()
                if suffix in [".zip", ".zipx"]:
                    return "ZIP"
                # Java archive files of various types
                if suffix == ".jar":
                    return "JAR"
                if suffix == ".war":
                    return "WAR"
                if suffix == ".ear":
                    return "EAR"
                # Android packages
                if suffix == ".apk":
                    return "APK"
                # iOS/iPad applications
                if suffix == ".ipa":
                    return "IPA"
                # Windows app package
                if suffix == ".msix":
                    return "MSIX"
            # Magic for Java and Mach-O FAT Binary are the same
            if magic_bytes[:4] == b"\xca\xfe\xba\xbe":
                # Distinguish them the same way file magic and Apple do
                # https://opensource.apple.com/source/file/file-80.40.2/file/magic/Magdir/cafebabe.auto.html
                # https://github.com/file/file/blob/master/magic/Magdir/cafebabe
                if int.from_bytes(magic_bytes[4:8], byteorder="big", signed=False) <= 30:
                    return "MACHOFAT"
                return "JAVACLASS"
            if magic_bytes[:4] == b"\xbe\xba\xfe\xca":
                return "MACHOFAT"
            if magic_bytes[:4] in [b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca"]:
                return "MACHOFAT64"
            # Apple fat EFI binaries
            if magic_bytes[:4] == b"\x0e\xf1\xfa\b9":
                return "EFIFAT"
            # NOTE: the MACH032 and MACHO64 (normal byte order) magic may be located
            # at offset 0x1000 in some files
            if magic_bytes[:4] in [b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe"]:
                return "MACHO32"
            if magic_bytes[:4] in [b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe"]:
                return "MACHO64"
            # https://releases.llvm.org/2.7/docs/BitCodeFormat.html#magic
            if magic_bytes[:4] == b"\xde\xc0\x17\x0b":
                return "LLVM_BITCODE"
            if magic_bytes[:4] == b"BC\xc0\xde":
                return "LLVM_IR"
            # Need to check both small and big endian for a.out
            a_out_magic = [0x111, 0x108, 0x107, 0x0CC, 0x10B]
            if (
                int.from_bytes(magic_bytes[:4], byteorder="big", signed=False) & 0xFFFF
                in a_out_magic
            ):
                return "A.OUT big"
            if (
                int.from_bytes(magic_bytes[:4], byteorder="little", signed=False) & 0xFFFF
                in a_out_magic
            ):
                return "A.OUT little"
            if (
                int.from_bytes(magic_bytes[:2], byteorder="little", signed=False)
                in COFF_MAGIC_TARGET_NAME
            ):
                return "COFF"
            # XCOFF:
            # https://www.ibm.com/docs/en/aix/7.3?topic=formats-xcoff-object-file-format
            if magic_bytes[:2] == "\x1d\x00":
                return "XCOFF32"
            if magic_bytes[:2] == "\xf7\x01":
                return "XCOFF64"
            # ECOFF:
            # https://web.archive.org/web/20160305114748/http://h41361.www4.hp.com/docs/base_doc/DOCUMENTATION/V50A_ACRO_SUP/OBJSPEC.PDF
            if magic_bytes[:2] in ("\x83\x01", "\x88\x01", "\x8f\x01"):
                return "ECOFF"
            # AR:
            # https://www.garykessler.net/library/file_sigs.html
            if magic_bytes[:8] == b"!<arch>\n":
                return "AR_LIB"
            # OMF:
            # https://github.com/file/file/blob/c8bba134ac1f3c9f5/magic/Magdir/msvc#L22
            if (
                int.from_bytes(magic_bytes[0:4], byteorder="big", signed=False) & 0xFF0F80FF
            ) == 0xF00D0000:
                return "OMF_LIB"
            # U-Boot/uImage
            # https://github.com/u-boot/u-boot/blob/master/include/image.h#L313
            if magic_bytes[:4] == b"\x27\x05\x19\x56":
                return "UIMAGE"
            # zlib:
            # https://www.rfc-editor.org/rfc/rfc1950
            if len(magic_bytes) >= 2:
                cmf = magic_bytes[0]
                flg = magic_bytes[1]
                cm = cmf & 0x0F
                if cm == 8:
                    if (cmf * 256 + flg) % 31 == 0:
                        return "ZLIB"
            # cpio:
            # https://commons.apache.org/proper/commons-compress/apidocs/org/apache/commons/compress/archivers/cpio/CpioArchiveEntry.html
            if int.from_bytes(magic_bytes[:2], byteorder="big", signed=False) == 0o70707:
                return "CPIO_BIN big"
            if int.from_bytes(magic_bytes[:2], byteorder="little", signed=False) == 0o70707:
                return "CPIO_BIN little"
            if magic_bytes[:6] == b"070707":
                return "CPIO_ASCII_OLD"
            if magic_bytes[:6] == b"070701":
                return "CPIO_ASCII_NEW"
            if magic_bytes[:6] == b"070702":
                return "CPIO_ASCII_NEW_CRC"
            # zstd:
            # https://datatracker.ietf.org/doc/html/rfc8878
            if magic_bytes[:4] == b"\x28\xb5\x2f\xfd":
                return "ZSTANDARD"
            if magic_bytes[:4] == b"\x37\xa4\x30\xec":
                return "ZSTANDARD_DICTIONARY"
            # iso:
            # https://en.wikipedia.org/wiki/List_of_file_signatures
            for offset in (0x8001, 0x8801, 0x9001):
                f.seek(offset)
                iso_bytes = f.read(5)
                if iso_bytes == b"CD001":
                    return "ISO_9660_CD"
            f.seek(0)

            # MacOS dmg:
            # https://en.wikipedia.org/wiki/List_of_file_signatures
            file_size = f.seek(0, os.SEEK_END)
            if file_size >= 512:
                f.seek(-512, os.SEEK_END)
                macos_bytes = f.read(4)
                if macos_bytes[0:4] == b"koly":
                    return "MACOS_DMG"

            # rpm:
            # https://rpm-software-management.github.io/rpm/manual/
            if magic_bytes[:4] == b"\xed\xab\xee\xdb":
                return "RPM Package"

            return None
    except FileNotFoundError:
        return None
