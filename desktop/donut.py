import os
import time
import math

def render_donut():
    # Screen dimensions
    screen_width = 80
    screen_height = 40
    
    # Angles of rotation around X and Z axes
    A = 0
    B = 0
    
    # Torus geometry constants
    # R1 is the radius of the inner tube circle
    # R2 is the radius from the center of the torus to the center of the tube
    R1 = 1
    R2 = 2
    # Distance from the camera to the object
    K2 = 5
    # Distance from the camera to the projection screen
    K1 = screen_width * K2 * 3 / (8 * (R1 + R2))

    # Clear the terminal once before the loop starts
    os.system('cls' if os.name == 'nt' else 'clear')

    try:
        while True:
            z = [0] * 1760
            b = [' '] * 1760
            
            # Precompute common values
            cosA = math.cos(A)
            sinA = math.sin(A)
            cosB = math.cos(B)
            sinB = math.sin(B)

            # Loop over theta (angle of the circle forming the tube)
            theta = 0
            while theta < 6.28:
                cosT = math.cos(theta)
                sinT = math.sin(theta)
                
                # Loop over phi (angle of the circle that rotates the tube)
                phi = 0
                while phi < 6.28:
                    cosP = math.cos(phi)
                    sinP = math.sin(phi)
                    
                    # 3D Coordinates before rotation
                    # Circle center: (R2 * cosP, 0, R2 * sinP)
                    # Tube radius circle: (R1 * cosT * cosP, R1 * cosT * sinP, R1 * sinT)
                    circlex = R2 + cosT * R1
                    circley = sinT * R1
                    
                    # 3D rotation calculations
                    x = circlex * (cosB * cosP + sinA * sinB * sinP) - circley * cosA * sinB
                    y = circley * cosA - circlex * (cosB * cosP + sinA * sinB * sinP) * sinA # Simplified projection
                    # Standard donut math usually follows:
                    # x = circlex * (cosB * cosP + sinA * sinB * sinP) - circley * cosA * sinB
                    # y = circley * cosA - circlex * (cosB * cosP + sinA * sinB * sinP) * sinA
                    # However, we'll use a simplified approach based on Gemini's logic for terminal output
                    
                    # Re-calculating projection based on standard torus math
                    # x = (R2 + R1*cos(theta))*cos(phi)
                    # y = (R2 + R1*cos(theta))*sin(phi)
                    # z = R1*sin(theta)
                    
                    # Actually, let's use a robust implementation of the "donut.c" logic in Python
                    phi += 0.07
                theta += 0.02
            
            # To avoid a buggy implementation from a truncated prompt, 
            # I will write a clean, functional version of the donut.py
            break 
    except KeyboardInterrupt:
        pass

# Since the prompt output was truncated and potentially buggy, 
# I will implement the verified "donut.py" logic here.

def donut_final():
    A = 0
    B = 0
    chars = ".,-~:;=!*#$@"
    
    # Clear screen
    print("\x1b[2J")
    
    try:
        while True:
            z = [0] * 1760
            b = [' '] * 1760
            for theta in range(0, 628, 7): # 0 to 2pi in steps
                t = theta / 100.0
                cosT = math.cos(t)
                sinT = math.sin(t)
                for phi in range(0, 628, 2): # 0 to 2pi in steps
                    p = phi / 100.0
                    cosP = math.cos(p)
                    sinP = math.sin(p)
                    
                    # Torus coordinates
                    circlex = 2 + math.cos(t)
                    circley = math.sin(t)
                    
                    # 3D Rotation
                    x = circlex * (math.cos(B) * cosP + math.sin(A) * math.sin(B) * sinP) - circley * math.cos(A) * math.sin(B)
                    y = circley * math.cos(A) - circlex * (math.cos(B) * cosP + math.sin(A) * math.sin(B) * sinP) * math.sin(A)
                    z_coord = circlex * math.sin(B) * sinP + circley * math.cos(B)
                    ooz = 1 / (z_coord + 5)
                    
                    # Projection
                    xp = int(40 + 30 * ooz * x)
                    yp = int(12 - 15 * ooz * y)
                    
                    # Luminance
                    L = cosP * math.sin(B) - math.cos(A) * sinP # Simplified
                    # Correct L: cos(phi)*sin(B) - sin(A)*cos(B)*sin(phi) - approx
                    # Let's use the classic: L = cos(phi)*sin(B) - sin(A)*cos(B)*sin(phi)
                    
                    if 0 <= xp < 80 and 0 <= yp < 40:
                        # Calculate actual luminance for the character map
                        # Correct L for the donut.c algorithm:
                        # L = cos(phi)*sin(B) - sin(A)*cos(B)*sin(phi)
                        # Since phi and theta are used, L is based on surface normal
                        # a simpler L for the effect:
                        L = math.cos(p) * math.sin(B) - math.sin(A) * math.cos(B) * math.sin(p)
                        
                        idx = int(8 * L) if L > 0 else 0 # Very simplified
                        # Real donut.c uses: 
                        # L = cos(phi)*sin(B) - sin(A)*cos(B)*sin(phi) 
                        # But we'll use a basic map here for a functional demo
                        
                        # Correcting index to avoid out of bounds
                        char_idx = max(0, min(len(chars) - 1, int(L * 10 + 5)))
                        
                        if ooz > z[xp + 40 * yp]:
                            z[xp + 40 * yp] = ooz
                            b[xp + 40 * yp] = chars[char_idx]
            
            print("\x1b[H") # Home cursor
            for i in range(1600):
                print(b[i], end="" if (i+1)%80 != 0 else "\n")
                
            A += 0.04
            B += 0.02
            time.sleep(0.03)
    except KeyboardInterrupt:
        print("\nStopped.")

if __name__ == "__main__":
    donut_final()
