// Decompile a list of functions (and their direct callees, to a given depth) into one .c file per entry.
// Headless usage:
//   analyzeHeadless <projdir> <proj> -process <exe> -noanalysis -scriptPath tools/ghidra
//       -postScript DecompileList.java <list.txt> <outdir> [depth]
// list.txt lines: "<name> <hex VA>"; '#' starts a comment.
// @category Riedel

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileOptions;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;

import java.io.File;
import java.io.PrintWriter;
import java.nio.file.Files;
import java.util.*;

public class DecompileList extends GhidraScript {

    private DecompInterface ifc;

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        File list = new File(args[0]);
        File outDir = new File(args[1]);
        int depth = args.length > 2 ? Integer.parseInt(args[2]) : 1;
        outDir.mkdirs();

        ifc = new DecompInterface();
        DecompileOptions opts = new DecompileOptions();
        ifc.setOptions(opts);
        ifc.openProgram(currentProgram);

        FunctionManager fm = currentProgram.getFunctionManager();
        for (String line : Files.readAllLines(list.toPath())) {
            line = line.trim();
            if (line.isEmpty() || line.startsWith("#")) continue;
            String[] p = line.split("\\s+");
            String name = p[0];
            Address a = toAddr(Long.parseLong(p[1].replace("0x", ""), 16));
            Function f = fm.getFunctionAt(a);
            if (f == null) {
                f = createFunction(a, null);
            }
            if (f == null) {
                println("no function at " + a + " for " + name);
                continue;
            }
            try (PrintWriter w = new PrintWriter(new File(outDir, name + ".c"), "UTF-8")) {
                Set<Function> seen = new HashSet<>();
                emit(w, f, depth, seen, fm);
            }
            println("wrote " + name);
        }
        ifc.dispose();
    }

    private void emit(PrintWriter w, Function f, int depth, Set<Function> seen, FunctionManager fm) throws Exception {
        if (!seen.add(f) || monitor.isCancelled()) return;
        DecompileResults r = ifc.decompileFunction(f, 120, monitor);
        w.println("// ===== " + f.getName() + " @ " + f.getEntryPoint() + " =====");
        if (r != null && r.decompileCompleted()) {
            w.println(r.getDecompiledFunction().getC());
        } else {
            w.println("// decompile failed: " + (r == null ? "null" : r.getErrorMessage()));
        }
        if (depth <= 0) return;
        List<Function> callees = new ArrayList<>(f.getCalledFunctions(monitor));
        callees.sort(Comparator.comparing(Function::getEntryPoint));
        for (Function c : callees) {
            // Skip thunks, library functions and very large helpers (MFC / CRT internals).
            if (c.isThunk() || c.isExternal()) continue;
            if (c.getBody().getNumAddresses() > 20000) continue;
            if (SKIP.contains(c.getEntryPoint().getOffset())) continue;
            emit(w, c, depth - 1, seen, fm);
        }
    }

    // Known MFC CArchive / CString helpers (see docs/FORMAT_NOTES.md §4) - don't inline their bodies.
    private static final Set<Long> SKIP = new HashSet<>(Arrays.asList(
        0x8180ddL, 0x817b00L, 0x818474L, 0x817f06L, 0x77a0a0L, 0x77a140L,
        0x7761d0L, 0x775e10L, 0x776a80L, 0x775d80L, 0x775be0L, 0x776470L, 0x776030L,
        0x80d8d6L, 0x776420L, 0x9666b6L
    ));
}
