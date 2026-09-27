// Decompile every function whose entry lies in [start, end) into one .c file per function.
// Headless usage:
//   analyzeHeadless <projdir> <proj> -process <exe> -noanalysis -readOnly -scriptPath tools/ghidra
//       -postScript DecompileRange.java <hex start> <hex end> <outdir>
// @category Riedel

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileOptions;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;

import java.io.File;
import java.io.PrintWriter;

public class DecompileRange extends GhidraScript {

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        Address start = toAddr(Long.parseLong(args[0].replace("0x", ""), 16));
        Address end = toAddr(Long.parseLong(args[1].replace("0x", ""), 16));
        File outDir = new File(args[2]);
        outDir.mkdirs();

        DecompInterface ifc = new DecompInterface();
        ifc.setOptions(new DecompileOptions());
        ifc.openProgram(currentProgram);

        int n = 0;
        FunctionIterator it = currentProgram.getFunctionManager().getFunctions(start, true);
        while (it.hasNext()) {
            Function f = it.next();
            if (f.getEntryPoint().compareTo(end) >= 0) break;
            DecompileResults r = ifc.decompileFunction(f, 60, monitor);
            if (r == null || !r.decompileCompleted()) continue;
            try (PrintWriter w = new PrintWriter(new File(outDir, f.getEntryPoint().toString() + ".c"), "UTF-8")) {
                w.println("// ===== " + f.getName() + " @ " + f.getEntryPoint() + " =====");
                w.println(r.getDecompiledFunction().getC());
            }
            n++;
        }
        ifc.dispose();
        println("decompiled " + n + " functions");
    }
}
