class PerformanceCalculator {
  constructor() {
    this.startTime = null;
    this.endTime = null;
  }

  start() {
    this.startTime = new Date();
  }

  end() {
    this.endTime = new Date();
  }

  calculateDuration() {
    var duration = 0;
    if (this.startTime && this.endTime) {
      duration = this.endTime - this.startTime;

    } else {
      throw new Error("Performance calculation is incomplete. Make sure to call the start() and end() methods.");
    }
    return this.getFormattedDuration(duration);
  }
  getFormattedDuration(duration) {
    const seconds = Math.floor(duration / 1000); // Convert milliseconds to seconds

    if (seconds > 20) {
      return "🐢"; // Tortoise emoji for durations longer than 20 seconds
    } else {
      const animals = ["🦘","🐆","🦌", "🐕","🐅", "🐈"]; // Updated array with a faster animal emoji (tiger)
      const remainingSeconds = seconds - 1; // Subtract 1 second for the tortoise

      if (remainingSeconds >= 0 && remainingSeconds < 5) {
        return animals[remainingSeconds]; // Return the corresponding animal emoji based on the remaining seconds
      } else {
        return "🦅"; // Hourglass emoji for durations less than 1 second or more than 5 seconds
      }
    }
  }
}
    
export {
  PerformanceCalculator
};