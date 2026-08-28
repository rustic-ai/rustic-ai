// Initialize Mermaid for diagrams in code blocks
document.addEventListener("DOMContentLoaded", function() {
  // Find all code blocks that contain mermaid syntax
  const codeBlocks = document.querySelectorAll('pre > code');
  
  codeBlocks.forEach((block, index) => {
    const text = block.textContent.trim();
    
    // Check if this is a mermaid diagram
    if (text.startsWith('flowchart') || 
        text.startsWith('sequenceDiagram') || 
        text.startsWith('graph') ||
        text.startsWith('gantt') ||
        text.startsWith('classDiagram') ||
        text.startsWith('stateDiagram') ||
        text.startsWith('erDiagram') ||
        text.startsWith('journey') ||
        text.startsWith('pie')) {
      
      // Create a new div with mermaid class
      const mermaidDiv = document.createElement('div');
      mermaidDiv.className = 'mermaid';
      mermaidDiv.textContent = text;
      
      // Replace the pre element with our mermaid div
      const pre = block.parentElement;
      pre.parentElement.replaceChild(mermaidDiv, pre);
    }
  });
  
  // Initialize mermaid
  if (typeof mermaid !== 'undefined') {
    mermaid.initialize({ 
      startOnLoad: true,
      theme: 'default',
      securityLevel: 'loose'
    });
    mermaid.init(undefined, document.querySelectorAll('.mermaid'));
  }
});
