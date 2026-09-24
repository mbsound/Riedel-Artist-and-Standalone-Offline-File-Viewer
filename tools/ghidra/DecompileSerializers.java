// Decompile Director's per-class Serialize functions with CArchive typed and MFC helpers named,
// following callees and keeping only functions that touch the archive.
// Headless usage:
//   analyzeHeadless <projdir> <proj> -process <exe> -noanalysis -scriptPath tools/ghidra
//       -postScript DecompileSerializers.java <list.txt> <outdir> [depth]
// list.txt lines: "<name> <hex VA>"; '#' starts a comment.
// @category Riedel

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileOptions;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.pcode.HighFunctionDBUtil;
import ghidra.program.model.symbol.SourceType;

import java.io.File;
import java.io.PrintWriter;
import java.nio.file.Files;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class DecompileSerializers extends GhidraScript {

    // Helpers identified in Director 8.9.D2 (see docs/FORMAT_NOTES.md §4).
    private static final Object[][] NAMES = {
        {0x8180ddL, "CArchive_Flush"},
        {0x817f99L, "CArchive_FillBuffer"},
        {0x817b00L, "AfxThrowArchiveException"},
        {0x80d513L, "AfxThrowInvalidArgException"},
        {0x776420L, "AfxThrowOleException"},
        {0x818474L, "CArchive_Write"},
        {0x817f06L, "CArchive_WriteCount"},
        {0x77a0a0L, "Ar_WriteU32"},
        {0x77a140L, "Ar_ReadU32"},
        {0xddad60L, "Ar_WriteString"},
        {0xddb0e0L, "Ar_ReadString"},
        {0x7d58e0L, "Ar_ReadWString"},
        {0x7761d0L, "CString_GetBuffer"},
        {0x776a80L, "CString_Format"},
        {0x775d80L, "CString_Init"},
        {0x775be0L, "CString_Release"},
        {0x776470L, "CString_Assign"},
        {0x779f50L, "CString_Equal"},
        {0x96b99dL, "__RTDynamicCast"},
    };
    private static final long FILE_VERSION_GLOBAL = 0x12a8968L;

    private DecompInterface ifc;
    private DataType archivePtr;
    private final Set<Long> skip = new HashSet<>();
    private final Set<Function> retyped = new HashSet<>();

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        File list = new File(args[0]);
        File outDir = new File(args[1]);
        int depth = args.length > 2 ? Integer.parseInt(args[2]) : 3;
        outDir.mkdirs();

        setup();
        ifc = new DecompInterface();
        ifc.setOptions(new DecompileOptions());
        ifc.openProgram(currentProgram);

        FunctionManager fm = currentProgram.getFunctionManager();
        for (String line : Files.readAllLines(list.toPath())) {
            line = line.trim();
            if (line.isEmpty() || line.startsWith("#")) continue;
            String[] p = line.split("\\s+");
            Address a = toAddr(Long.parseLong(p[1].replace("0x", ""), 16));
            Function f = fm.getFunctionAt(a);
            if (f == null) f = createFunction(a, null);
            if (f == null) { println("no function at " + a); continue; }
            try (PrintWriter w = new PrintWriter(new File(outDir, p[0] + ".c"), "UTF-8")) {
                emit(w, f, depth, new HashSet<>(), true);
            }
            println("wrote " + p[0]);
        }
        ifc.dispose();
    }

    private void setup() throws Exception {
        for (Object[] n : NAMES) {
            long va = (Long) n[0];
            skip.add(va);
            Function f = getFunctionAt(toAddr(va));
            if (f == null) f = createFunction(toAddr(va), null);
            if (f != null) f.setName((String) n[1], SourceType.USER_DEFINED);
        }
        createLabel(toAddr(FILE_VERSION_GLOBAL), "g_FileVersion", true, SourceType.USER_DEFINED);

        DataTypeManager dtm = currentProgram.getDataTypeManager();
        StructureDataType s = new StructureDataType("CArchive", 0x40);
        s.replaceAtOffset(0x18, UnsignedIntegerDataType.dataType, 4, "m_nMode", "bit0 = loading");
        s.replaceAtOffset(0x20, PointerDataType.dataType, 4, "m_pDocument", null);
        s.replaceAtOffset(0x24, PointerDataType.dataType, 4, "m_lpBufStart", null);
        s.replaceAtOffset(0x28, new PointerDataType(ByteDataType.dataType), 4, "m_lpBufCur", null);
        s.replaceAtOffset(0x2c, new PointerDataType(ByteDataType.dataType), 4, "m_lpBufMax", null);
        DataType arch = dtm.addDataType(s, DataTypeConflictHandler.REPLACE_HANDLER);
        archivePtr = new PointerDataType(arch);
    }

    private static final Pattern ALIAS = Pattern.compile("(\\w+) = \\(?[\\w\\s\\*\\(\\)]*?\\)?param_(\\d);");

    /** Find which parameter is used like a CArchive (offsets 0x18/0x28/0x2c or word indices 6/10/0xb). */
    private int archiveParam(String c) {
        Map<String, Integer> names = new HashMap<>();
        for (int i = 1; i <= 6; i++) names.put("param_" + i, i);
        Matcher m = ALIAS.matcher(c);
        while (m.find()) names.put(m.group(1), Integer.parseInt(m.group(2)));
        for (Map.Entry<String, Integer> e : names.entrySet()) {
            String v = Pattern.quote(e.getKey());
            boolean cur = Pattern.compile(v + " \\+ 0x28\\)|" + v + "\\[10\\]|" + v + "->m_lpBufCur").matcher(c).find();
            boolean max = Pattern.compile(v + " \\+ 0x2c\\)|" + v + "\\[0xb\\]|" + v + "->m_lpBufMax").matcher(c).find();
            if (cur && max) return e.getValue();
        }
        return 0;
    }

    private String decompile(Function f) {
        DecompileResults r = ifc.decompileFunction(f, 180, monitor);
        if (r == null || !r.decompileCompleted()) return null;
        return r.getDecompiledFunction().getC();
    }

    private void emit(PrintWriter w, Function f, int depth, Set<Function> seen, boolean root) throws Exception {
        if (!seen.add(f) || monitor.isCancelled()) return;
        String c = decompile(f);
        if (c == null) {
            if (root) w.println("// ===== " + f.getName() + " @ " + f.getEntryPoint() + " : decompile failed");
            return;
        }
        int ap = archiveParam(c);
        if (ap > 0 && !retyped.contains(f)) {
            try {
                if (ap > f.getParameterCount()) {
                    // Parameters exist only in the decompiler's view; commit them so they can be retyped.
                    DecompileResults r = ifc.decompileFunction(f, 180, monitor);
                    HighFunctionDBUtil.commitParamsToDatabase(r.getHighFunction(), true,
                        HighFunctionDBUtil.ReturnCommitOption.NO_COMMIT, SourceType.USER_DEFINED);
                }
                Parameter prm = f.getParameter(ap - 1);
                prm.setDataType(archivePtr, SourceType.USER_DEFINED);
                prm.setName("ar", SourceType.USER_DEFINED);
                retyped.add(f);
                String c2 = decompile(f);
                if (c2 != null) c = c2;
            } catch (Exception e) {
                println("retype failed " + f.getName() + ": " + e);
            }
        }
        boolean relevant = root || ap > 0 || c.contains("Ar_Read") || c.contains("Ar_Write")
            || c.contains("CArchive_") || c.contains("g_FileVersion");
        if (relevant) {
            w.println("// ===== " + f.getName() + " @ " + f.getEntryPoint() + " =====");
            w.println(c);
        }
        if (depth <= 0 || !relevant) return;
        List<Function> callees = new ArrayList<>(f.getCalledFunctions(monitor));
        callees.sort(Comparator.comparing(Function::getEntryPoint));
        for (Function cf : callees) {
            if (cf.isThunk() || cf.isExternal()) continue;
            if (skip.contains(cf.getEntryPoint().getOffset())) continue;
            if (cf.getBody().getNumAddresses() > 30000) continue;
            emit(w, cf, depth - 1, seen, false);
        }
    }
}
