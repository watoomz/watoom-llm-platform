#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "WatooMWanderComponent.generated.h"

/**
 * Roaming for NPCs and creatures without a navmesh or behaviour tree: on the server, walk toward a random point within Radius
 * of where the character started, wait, pick another. Steers with AddMovementInput, so the CharacterMovement component keeps it
 * on the ground and the anim BP sees a normal Speed. A blocked walk (moved < StuckCm in StuckSeconds) picks a new point.
 * Off unless bEnabled (unreal_combat.py: character defaults "Wander.bEnabled": true, "Wander.Radius": 3000).
 * Points whose ground lies below MinGroundZ (e.g. the sea surface) are rejected, so land creatures stay out of the water.
 * Placed characters are possessed by an AIController by default (ACharacter AutoPossessAI = PlacedInWorld), which is what lets
 * AddMovementInput move them. Dead characters (WatooM State.Dead) stop.
 */
UCLASS(ClassGroup = (WatooM), meta = (BlueprintSpawnableComponent))
class WATOOMCOMBAT_API UWatooMWanderComponent : public UActorComponent
{
	GENERATED_BODY()
public:
	UWatooMWanderComponent();

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Wander") bool bEnabled = false;
	/** cm around the start point */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Wander") float Radius = 2000.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Wander") float WaitMin = 1.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Wander") float WaitMax = 4.f;
	/** 0..1 of the movement component's max walk speed */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Wander") float SpeedScale = 0.5f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Wander") float AcceptRadius = 150.f;
	/** Reject targets whose ground is below this Z (cm); very low = no limit. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Wander") float MinGroundZ = -1.0e7f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Wander") float StuckSeconds = 2.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Wander") float StuckCm = 20.f;

	UFUNCTION(BlueprintPure, Category = "Wander") FVector GetTarget() const { return Target; }
	UFUNCTION(BlueprintPure, Category = "Wander") FVector GetHome() const { return Home; }

	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

protected:
	virtual void BeginPlay() override;
	bool PickTarget();

	FVector Home = FVector::ZeroVector;
	FVector Target = FVector::ZeroVector;
	FVector LastCheckPos = FVector::ZeroVector;
	float WaitLeft = 0.f;
	float StuckClock = 0.f;
	bool bHasTarget = false;
};
