function sortTable(i, n) {
  var table, rows, switching, x, y, shouldSwitch, dir, switchcount = 0;
  table = document.getElementById("sortable" + i);
  switching = true;
  dir = "asc"; // Set the sorting direction to ascending by default

  while (switching) {
    switching = false;
    rows = table.rows;

    // Loop through all table rows (except the first, which contains table headers)
    for (var j = 1; j < (rows.length - 1); j++) {
      shouldSwitch = false;
      x = rows[j].getElementsByTagName("TD")[n];
      y = rows[j + 1].getElementsByTagName("TD")[n];

      // Try to parse the content of the cells as numbers
      var xContent = parseFloat(x.innerHTML) || x.innerHTML.toLowerCase();  // Try to convert to a number, fallback to string
      var yContent = parseFloat(y.innerHTML) || y.innerHTML.toLowerCase();  // Try to convert to a number, fallback to string

      // Handle ascending sort
      if (dir == "asc") {
        if (xContent > yContent) {
          shouldSwitch = true;
          break;
        }
      // Handle descending sort
      } else if (dir == "desc") {
        if (xContent < yContent) {
          shouldSwitch = true;
          break;
        }
      }
    }

    if (shouldSwitch) {
      // Perform the switch and mark that a switch has been done
      rows[j].parentNode.insertBefore(rows[j + 1], rows[j]);
      switching = true;
      switchcount++;
    } else {
      // If no switch has been made and the direction is "asc", switch to "desc"
      if (switchcount == 0 && dir == "asc") {
        dir = "desc";
        switching = true;
      }
    }
  }
}

